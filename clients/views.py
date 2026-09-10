"""Client CRUD + profile views (spec §20–21, §48)."""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST
from django.views.generic import DetailView, FormView, ListView, TemplateView

from audit.models import AuditLog
from clients.forms import ClientFilterForm, ClientForm
from clients.models import Client
from clients.selectors import client_list
from clients.services import (
    archive_client,
    create_client,
    restore_client,
    update_client,
)
from core.permissions.capabilities import Capability, can
from core.permissions.decorators import require_capability
from core.permissions.mixins import CapabilityRequiredMixin
from core.querysets import assert_scoped

PAGE_SIZE = 25


class ClientListView(CapabilityRequiredMixin, LoginRequiredMixin, ListView):
    required_capability = Capability.CLIENTS_VIEW
    template_name = "clients/client_list.html"
    context_object_name = "clients"

    def get_queryset(self):
        self.filter_form = ClientFilterForm(self.request.GET or None)
        self.filter_form.is_valid()
        data = self.filter_form.cleaned_data if self.filter_form.is_bound else {}
        qs = client_list(
            user=self.request.user,
            query=data.get("q", ""),
            type=data.get("type", ""),
            status=data.get("status", ""),
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
            "clients": page.object_list,
            "total_count": paginator.count,
            "querystring": f"{querystring}&" if querystring else "",
            "can_manage": can(self.request.user, Capability.CLIENTS_MANAGE),
        }


class ClientDetailView(CapabilityRequiredMixin, LoginRequiredMixin, DetailView):
    required_capability = Capability.CLIENTS_VIEW
    template_name = "clients/client_detail.html"
    context_object_name = "client"

    def get_queryset(self):
        qs = Client.objects.for_user(self.request.user).select_related("created_by", "updated_by")
        assert_scoped(qs)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from contracts.selectors import client_contracts
        from documents.selectors import client_documents

        user = self.request.user
        client = self.object
        ctx["can_manage"] = can(user, Capability.CLIENTS_MANAGE)
        ctx["can_view_sensitive"] = can(user, Capability.CLIENTS_VIEW_SENSITIVE)
        ctx["can_documents"] = can(user, Capability.DOCUMENTS_VIEW)
        ctx["can_documents_manage"] = can(user, Capability.DOCUMENTS_MANAGE)
        ctx["client_documents"] = client_documents(client)[:8]
        ctx["can_contracts"] = can(user, Capability.CONTRACTS_VIEW)
        ctx["can_contracts_manage"] = can(user, Capability.CONTRACTS_MANAGE)
        ctx["client_contracts"] = client_contracts(client)[:8]
        ctx["activity"] = AuditLog.objects.filter(
            entity_type="clients.client", entity_id=str(client.pk)
        ).select_related("actor")[:20]

        # Financial summary (§21) — real figures, but only for finance viewers.
        ctx["can_finance"] = can(user, Capability.FINANCE_VIEW)
        ctx["can_finance_manage"] = can(user, Capability.FINANCE_MANAGE)
        if ctx["can_finance"]:
            from finance.selectors import client_financials, client_invoices, client_payments

            ctx["finance_summary"] = client_financials(client)
            ctx["client_invoices"] = client_invoices(client)[:6]
            ctx["client_payments"] = client_payments(client)[:6]

        # Profile tabs whose modules do not exist yet (spec §21).
        ctx["disabled_tabs"] = [_("القضايا")]
        return ctx


class _ClientFormMixin(CapabilityRequiredMixin, LoginRequiredMixin, FormView):
    required_capability = Capability.CLIENTS_MANAGE
    form_class = ClientForm
    template_name = "clients/client_form.html"

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "user": self.request.user}

    def get_success_url(self):
        return reverse("clients:detail", args=[self.object.pk])


class ClientCreateView(_ClientFormMixin):
    def form_valid(self, form):
        self.object = create_client(
            actor=self.request.user, data=form.cleaned_data, request=self.request
        )
        messages.success(
            self.request,
            _("تم إنشاء العميل %(n)s.") % {"n": self.object.client_number},
        )
        return redirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), "is_create": True}


class ClientUpdateView(_ClientFormMixin):
    def dispatch(self, request, *args, **kwargs):
        self.client_obj = get_object_or_404(Client.objects.for_user(request.user), pk=kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "instance": self.client_obj}

    def form_valid(self, form):
        self.object = update_client(
            actor=self.request.user,
            client=self.client_obj,
            data=form.cleaned_data,
            request=self.request,
        )
        messages.success(self.request, _("تم حفظ التعديلات."))
        return redirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        return {
            **super().get_context_data(**kwargs),
            "is_create": False,
            "client": self.client_obj,
        }


@require_POST
@require_capability(Capability.CLIENTS_MANAGE)
def client_archive(request, pk):
    client = get_object_or_404(Client.objects.for_user(request.user), pk=pk)
    archive_client(actor=request.user, client=client, request=request)
    messages.warning(request, _("تمت أرشفة العميل."))
    return redirect("clients:detail", pk=pk)


@require_POST
@require_capability(Capability.CLIENTS_MANAGE)
def client_restore(request, pk):
    client = get_object_or_404(Client.objects.for_user(request.user), pk=pk)
    restore_client(actor=request.user, client=client, request=request)
    messages.success(request, _("تمت استعادة العميل."))
    return redirect("clients:detail", pk=pk)


class ClientArchiveConfirmView(CapabilityRequiredMixin, LoginRequiredMixin, TemplateView):
    required_capability = Capability.CLIENTS_MANAGE
    template_name = "clients/client_confirm_archive.html"

    def get_context_data(self, **kwargs):
        client = get_object_or_404(Client.objects.for_user(self.request.user), pk=self.kwargs["pk"])
        return {**super().get_context_data(**kwargs), "client": client}
