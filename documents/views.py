"""
Document list, detail, upload, metadata edit, retire, and the **private
download** (spec §34–36, §46, docs/adr/0030).

Every staff member may view + download documents (``documents.view``); upload /
edit / retire require ``documents.manage``. Files are private: the only way to a
file's bytes is ``document_download`` — authenticated, capability-gated,
object-scoped (404 outside scope or retired), and audited. Nothing is ever
web-served from the documents storage.
"""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import DetailView, FormView, ListView

from cases.models import Case
from clients.models import Client
from core.permissions.capabilities import Capability, can
from core.permissions.decorators import require_capability
from core.permissions.mixins import CapabilityRequiredMixin
from core.querysets import assert_scoped
from documents import services
from documents.forms import DocumentEditForm, DocumentFilterForm, DocumentUploadForm
from documents.models import Document
from documents.selectors import document_list

PAGE_SIZE = 25


def _get_document(user, pk) -> Document:
    qs = (
        Document.objects.for_user(user)
        .alive()
        .select_related("case", "client", "uploaded_by", "updated_by")
    )
    assert_scoped(qs)
    return get_object_or_404(qs, pk=pk)


class DocumentListView(CapabilityRequiredMixin, LoginRequiredMixin, ListView):
    required_capability = Capability.DOCUMENTS_VIEW
    template_name = "documents/document_list.html"
    context_object_name = "documents"

    def get_queryset(self):
        self.filter_form = DocumentFilterForm(self.request.GET or None)
        self.filter_form.is_valid()
        data = self.filter_form.cleaned_data if self.filter_form.is_bound else {}
        qs = document_list(
            user=self.request.user,
            query=data.get("q", ""),
            document_type=data.get("document_type", ""),
            case_id=self.request.GET.get("case", ""),
            client_id=self.request.GET.get("client", ""),
        )
        assert_scoped(qs)
        return qs

    def get_context_data(self, **kwargs):
        paginator = Paginator(self.object_list, PAGE_SIZE)
        page = paginator.get_page(self.request.GET.get("page"))
        params = self.request.GET.copy()
        params.pop("page", None)
        querystring = params.urlencode()
        return {
            **super().get_context_data(object_list=page.object_list, **kwargs),
            "filter_form": self.filter_form,
            "page_obj": page,
            "documents": page.object_list,
            "total_count": paginator.count,
            "querystring": f"{querystring}&" if querystring else "",
            "can_manage": can(self.request.user, Capability.DOCUMENTS_MANAGE),
        }


class DocumentDetailView(CapabilityRequiredMixin, LoginRequiredMixin, DetailView):
    required_capability = Capability.DOCUMENTS_VIEW
    template_name = "documents/document_detail.html"
    context_object_name = "document"

    def get_object(self, queryset=None):
        return _get_document(self.request.user, self.kwargs["pk"])

    def get_context_data(self, **kwargs):
        return {
            **super().get_context_data(**kwargs),
            "can_manage": can(self.request.user, Capability.DOCUMENTS_MANAGE),
        }


class DocumentUploadView(CapabilityRequiredMixin, LoginRequiredMixin, FormView):
    required_capability = Capability.DOCUMENTS_MANAGE
    form_class = DocumentUploadForm
    template_name = "documents/document_form.html"

    def _prefill(self):
        case_id = self.request.GET.get("case")
        client_id = self.request.GET.get("client")
        initial = {}
        if (
            str(case_id).isdigit()
            and Case.objects.for_user(self.request.user).filter(pk=case_id).exists()
        ):
            initial["case"] = case_id
        if (
            str(client_id).isdigit()
            and Client.objects.for_user(self.request.user).filter(pk=client_id).exists()
        ):
            initial["client"] = client_id
        return initial

    def get_form_kwargs(self):
        return {
            **super().get_form_kwargs(),
            "user": self.request.user,
            "initial": {**self.get_initial(), **self._prefill()},
        }

    def form_valid(self, form):
        cd = form.cleaned_data
        doc = services.create_document(
            actor=self.request.user,
            uploaded_file=cd["file"],
            validated=form.validated,
            data={
                "name": cd["name"],
                "document_type": cd["document_type"],
                "description": cd.get("description", ""),
                "case": cd.get("case"),
                "client": cd.get("client"),
            },
            request=self.request,
        )
        messages.success(self.request, _("تم رفع المستند."))
        return redirect("documents:detail", pk=doc.pk)

    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), "is_create": True}


class DocumentUpdateView(CapabilityRequiredMixin, LoginRequiredMixin, FormView):
    required_capability = Capability.DOCUMENTS_MANAGE
    form_class = DocumentEditForm
    template_name = "documents/document_form.html"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            self.doc = _get_document(request.user, kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "user": self.request.user, "instance": self.doc}

    def form_valid(self, form):
        services.update_document(
            actor=self.request.user,
            document=self.doc,
            data=form.cleaned_data,
            request=self.request,
        )
        messages.success(self.request, _("تم حفظ التعديلات."))
        return redirect("documents:detail", pk=self.doc.pk)

    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), "is_create": False, "document": self.doc}


@require_GET
@require_capability(Capability.DOCUMENTS_VIEW)
def document_download(request, pk):
    """The only path to a document's bytes. Auth + capability + scope + audit."""
    document = _get_document(request.user, pk)
    try:
        handle = document.file.open("rb")
    except FileNotFoundError as exc:  # blob missing (out-of-band change) — reveal nothing
        raise Http404("Document file not available.") from exc
    services.record_download(actor=request.user, document=document, request=request)
    response = FileResponse(
        handle,
        as_attachment=True,
        filename=document.download_filename,
        content_type=document.content_type or "application/octet-stream",
    )
    response["X-Content-Type-Options"] = "nosniff"
    return response


@require_POST
@require_capability(Capability.DOCUMENTS_MANAGE)
def document_retire(request, pk):
    document = _get_document(request.user, pk)
    services.retire_document(actor=request.user, document=document, request=request)
    messages.success(request, _("تم سحب المستند."))
    return redirect(reverse("documents:list"))
