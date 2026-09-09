"""Case list, workspace, CRUD and sub-resource actions (spec §22–27, §48).

Every staff member may view every case (docs/adr/0008); mutating actions are
gated by ``cases.manage`` and the privileged notes by ``cases.view_confidential``.
Writes always go through ``cases.services`` so the timeline + audit trail stay
consistent.
"""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST
from django.views.generic import DetailView, FormView, ListView

from audit.models import AuditAction, AuditLog
from cases import services
from cases.forms import (
    CaseConfidentialForm,
    CaseFilterForm,
    CaseForm,
    CaseNoteForm,
    CasePartyForm,
    CaseStatusForm,
    SupportingLawyerForm,
)
from cases.models import Case, CaseConfidential, CaseStatus, NoteKind
from cases.selectors import case_list, case_parties
from core.permissions.capabilities import Capability, can
from core.permissions.decorators import require_capability
from core.permissions.mixins import CapabilityRequiredMixin
from core.querysets import assert_scoped
from documents.selectors import case_documents
from hearings.selectors import case_hearings
from tasks.selectors import case_deadlines, case_tasks

User = get_user_model()

PAGE_SIZE = 25

TAB_LINKS = (
    ("overview", _("نظرة عامة")),
    ("parties", _("الأطراف")),
    ("hearings", _("الجلسات")),
    ("tasks", _("المهام")),
    ("documents", _("المستندات")),
    ("notes", _("الملاحظات")),
    ("correspondence", _("المراسلات")),
    ("timeline", _("الخط الزمني")),
)
REAL_TABS = tuple(key for key, _label in TAB_LINKS)
DISABLED_TABS = (
    _("الفواتير"),
    _("المدفوعات"),
)


def _get_case(user, pk) -> Case:
    qs = Case.objects.for_user(user).select_related(
        "type", "client", "assigned_lawyer", "court", "created_by", "updated_by"
    )
    assert_scoped(qs)
    return get_object_or_404(qs, pk=pk)


class CaseListView(CapabilityRequiredMixin, LoginRequiredMixin, ListView):
    required_capability = Capability.CASES_VIEW
    template_name = "cases/case_list.html"
    context_object_name = "cases"

    def get_queryset(self):
        self.filter_form = CaseFilterForm(self.request.GET or None)
        self.filter_form.is_valid()
        data = self.filter_form.cleaned_data if self.filter_form.is_bound else {}
        qs = case_list(
            user=self.request.user,
            query=data.get("q", ""),
            status=data.get("status", ""),
            priority=data.get("priority", ""),
            type_id=getattr(data.get("type"), "pk", "") or "",
            lawyer_id=getattr(data.get("lawyer"), "pk", "") or "",
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
            "cases": page.object_list,
            "total_count": paginator.count,
            "querystring": f"{querystring}&" if querystring else "",
            "can_manage": can(self.request.user, Capability.CASES_MANAGE),
        }


class CaseDetailView(CapabilityRequiredMixin, LoginRequiredMixin, DetailView):
    required_capability = Capability.CASES_VIEW
    template_name = "cases/case_detail.html"
    context_object_name = "case"

    def get_object(self, queryset=None):
        return _get_case(self.request.user, self.kwargs["pk"])

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        case = self.object
        user = self.request.user
        tab = self.request.GET.get("tab", "overview")
        if tab not in REAL_TABS:
            tab = "overview"

        can_confidential = can(user, Capability.CASES_VIEW_CONFIDENTIAL)
        notes = list(case.notes.filter(deleted_at__isnull=True).select_related("author"))
        lawyer_links = list(case.lawyer_links.select_related("lawyer"))

        # The activity feed is visible to every staff member (cases.view); the
        # confidential-notes edit event must not appear there for anyone without
        # cases.view_confidential (docs/adr/0008 — the timeline never hints at
        # privileged content, and neither does this panel).
        activity = AuditLog.objects.filter(
            entity_type="cases.case", entity_id=str(case.pk)
        ).select_related("actor")
        if not can_confidential:
            activity = activity.exclude(action=AuditAction.CASE_CONFIDENTIAL_UPDATED)

        ctx.update(
            {
                "tab": tab,
                "tab_links": TAB_LINKS,
                "can_manage": can(user, Capability.CASES_MANAGE),
                "can_view_confidential": can_confidential,
                "can_documents": can(user, Capability.DOCUMENTS_VIEW),
                "can_documents_manage": can(user, Capability.DOCUMENTS_MANAGE),
                "parties": case_parties(case, lawyer_links=lawyer_links),
                "lawyer_links": lawyer_links,
                "notes": [n for n in notes if n.kind == NoteKind.GENERAL],
                "correspondence": [n for n in notes if n.kind == NoteKind.CORRESPONDENCE],
                "timeline": case.events.select_related("actor")[:100],
                "hearings": case_hearings(case),
                "case_tasks": case_tasks(case).order_by("-created_at"),
                "case_deadlines": case_deadlines(case),
                "case_documents": case_documents(case),
                "next_hearing": case.next_hearing,
                "status_form": CaseStatusForm(initial={"status": case.status}),
                "lawyer_form": SupportingLawyerForm(),
                "disabled_tabs": DISABLED_TABS,
                "activity": activity[:20],
            }
        )
        if can_confidential:
            ctx["confidential"] = case.confidential_or_none()
        return ctx


class _CaseFormMixin(CapabilityRequiredMixin, LoginRequiredMixin, FormView):
    required_capability = Capability.CASES_MANAGE
    form_class = CaseForm
    template_name = "cases/case_form.html"

    def get_success_url(self):
        return reverse("cases:detail", args=[self.object.pk])


class CaseCreateView(_CaseFormMixin):
    def form_valid(self, form):
        self.object = services.create_case(
            actor=self.request.user, data=form.cleaned_data, request=self.request
        )
        messages.success(self.request, _("تم إنشاء القضية %(n)s.") % {"n": self.object.case_number})
        return redirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), "is_create": True}


class CaseUpdateView(_CaseFormMixin):
    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            self.case_obj = _get_case(request.user, kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "instance": self.case_obj}

    def form_valid(self, form):
        self.object = services.update_case(
            actor=self.request.user,
            case=self.case_obj,
            data=form.cleaned_data,
            request=self.request,
        )
        messages.success(self.request, _("تم حفظ التعديلات."))
        return redirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        return {
            **super().get_context_data(**kwargs),
            "is_create": False,
            "case": self.case_obj,
        }


class CaseConfidentialUpdateView(CapabilityRequiredMixin, LoginRequiredMixin, FormView):
    required_capability = Capability.CASES_VIEW_CONFIDENTIAL
    form_class = CaseConfidentialForm
    template_name = "cases/case_confidential_form.html"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            self.case_obj = _get_case(request.user, kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        # Read path — do NOT create the row here (that would write an empty row +
        # an auditlog 'created' event on GET). The row is created by
        # services.set_confidential on save.
        instance = self.case_obj.confidential_or_none() or CaseConfidential(case=self.case_obj)
        return {**super().get_form_kwargs(), "instance": instance}

    def form_valid(self, form):
        services.set_confidential(
            actor=self.request.user,
            case=self.case_obj,
            legal_notes=form.cleaned_data["legal_notes"],
            internal_notes=form.cleaned_data["internal_notes"],
            request=self.request,
        )
        messages.success(self.request, _("تم حفظ الملاحظات السرية."))
        return redirect(reverse("cases:detail", args=[self.case_obj.pk]) + "?tab=overview")

    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), "case": self.case_obj}


class CasePartyAddView(CapabilityRequiredMixin, LoginRequiredMixin, FormView):
    required_capability = Capability.CASES_MANAGE
    form_class = CasePartyForm
    template_name = "cases/case_party_form.html"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            self.case_obj = _get_case(request.user, kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        services.add_party(
            actor=self.request.user,
            case=self.case_obj,
            data=form.cleaned_data,
            request=self.request,
        )
        messages.success(self.request, _("تمت إضافة الطرف."))
        return redirect(reverse("cases:detail", args=[self.case_obj.pk]) + "?tab=parties")

    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), "case": self.case_obj}


class CaseNoteAddView(CapabilityRequiredMixin, LoginRequiredMixin, FormView):
    required_capability = Capability.CASES_MANAGE
    form_class = CaseNoteForm
    template_name = "cases/case_note_form.html"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            self.case_obj = _get_case(request.user, kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        kind = self.request.GET.get("kind")
        return {"kind": kind} if kind in NoteKind.values else {}

    def form_valid(self, form):
        note = services.add_note(
            actor=self.request.user,
            case=self.case_obj,
            body=form.cleaned_data["body"],
            kind=form.cleaned_data["kind"],
            request=self.request,
        )
        messages.success(self.request, _("تمت إضافة الملاحظة."))
        tab = "correspondence" if note.kind == NoteKind.CORRESPONDENCE else "notes"
        return redirect(reverse("cases:detail", args=[self.case_obj.pk]) + f"?tab={tab}")

    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), "case": self.case_obj}


@require_POST
@require_capability(Capability.CASES_MANAGE)
def case_status(request, pk):
    case = _get_case(request.user, pk)
    form = CaseStatusForm(request.POST)
    if form.is_valid() and form.cleaned_data["status"] in CaseStatus.values:
        services.change_status(
            actor=request.user,
            case=case,
            new_status=form.cleaned_data["status"],
            request=request,
        )
        messages.success(request, _("تم تحديث حالة القضية."))
    else:
        messages.error(request, _("حالة غير صالحة."))
    return redirect("cases:detail", pk=pk)


@require_POST
@require_capability(Capability.CASES_MANAGE)
def case_lawyer_add(request, pk):
    case = _get_case(request.user, pk)
    form = SupportingLawyerForm(request.POST)
    if not form.is_valid():
        messages.error(request, _("تعذّرت إضافة المحامي."))
    elif services.add_supporting_lawyer(
        actor=request.user, case=case, lawyer=form.cleaned_data["lawyer"], request=request
    ):
        messages.success(request, _("تمت إضافة المحامي المساند."))
    else:
        messages.info(request, _("المحامي مضاف بالفعل إلى هذه القضية."))
    return redirect(reverse("cases:detail", args=[pk]) + "?tab=parties")


@require_POST
@require_capability(Capability.CASES_MANAGE)
def case_lawyer_remove(request, pk, user_pk):
    case = _get_case(request.user, pk)
    lawyer = get_object_or_404(User, pk=user_pk)
    if services.remove_supporting_lawyer(
        actor=request.user, case=case, lawyer=lawyer, request=request
    ):
        messages.success(request, _("تمت إزالة المحامي المساند."))
    else:
        messages.info(request, _("هذا المحامي ليس مساندًا في هذه القضية."))
    return redirect(reverse("cases:detail", args=[pk]) + "?tab=parties")


@require_POST
@require_capability(Capability.CASES_MANAGE)
def case_party_remove(request, pk, party_pk):
    case = _get_case(request.user, pk)
    party = get_object_or_404(case.parties, pk=party_pk)
    services.remove_party(actor=request.user, case=case, party=party, request=request)
    messages.success(request, _("تمت إزالة الطرف."))
    return redirect(reverse("cases:detail", args=[pk]) + "?tab=parties")
