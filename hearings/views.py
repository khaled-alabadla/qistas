"""Hearing list, detail, scheduling and lifecycle actions (spec §29–30).

Every staff member may view hearings (``hearings.view``); scheduling and lifecycle
transitions require ``hearings.manage``. Writes go through ``hearings.services`` so
the case timeline + audit trail stay consistent. A hearing is never deleted
(docs/adr/0022) — it is cancelled.
"""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST
from django.views.generic import DetailView, FormView, ListView

from cases.models import Case
from core.permissions.capabilities import Capability, can
from core.permissions.decorators import require_capability
from core.permissions.mixins import CapabilityRequiredMixin
from core.querysets import assert_scoped
from hearings import services
from hearings.forms import (
    HearingCancelForm,
    HearingCompleteForm,
    HearingFilterForm,
    HearingPostponeForm,
    HearingScheduleForm,
    HearingUpdateForm,
)
from hearings.models import Hearing
from hearings.selectors import hearing_list

PAGE_SIZE = 25


def _get_hearing(user, pk) -> Hearing:
    qs = Hearing.objects.for_user(user).select_related(
        "case", "case__client", "court", "lawyer", "created_by", "updated_by"
    )
    assert_scoped(qs)
    return get_object_or_404(qs, pk=pk)


def _get_case(user, pk) -> Case:
    qs = Case.objects.for_user(user)
    assert_scoped(qs)
    return get_object_or_404(qs, pk=pk)


class HearingListView(CapabilityRequiredMixin, LoginRequiredMixin, ListView):
    required_capability = Capability.HEARINGS_VIEW
    template_name = "hearings/hearing_list.html"
    context_object_name = "hearings"

    def get_queryset(self):
        self.filter_form = HearingFilterForm(self.request.GET or None)
        self.filter_form.is_valid()
        data = self.filter_form.cleaned_data if self.filter_form.is_bound else {}
        qs = hearing_list(
            user=self.request.user,
            query=data.get("q", ""),
            status=data.get("status", ""),
            hearing_type=data.get("hearing_type", ""),
            court_id=getattr(data.get("court"), "pk", "") or "",
            when=data.get("when") or "upcoming",
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
            "hearings": page.object_list,
            "total_count": paginator.count,
            "querystring": f"{querystring}&" if querystring else "",
            "can_manage": can(self.request.user, Capability.HEARINGS_MANAGE),
        }


class HearingDetailView(CapabilityRequiredMixin, LoginRequiredMixin, DetailView):
    required_capability = Capability.HEARINGS_VIEW
    template_name = "hearings/hearing_detail.html"
    context_object_name = "hearing"

    def get_object(self, queryset=None):
        return _get_hearing(self.request.user, self.kwargs["pk"])

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        hearing = self.object
        ctx.update(
            {
                "can_manage": can(self.request.user, Capability.HEARINGS_MANAGE),
                "follow_ups": hearing.follow_ups.select_related("court").order_by("scheduled_at"),
                "cancel_form": HearingCancelForm(),
            }
        )
        return ctx


class HearingScheduleView(CapabilityRequiredMixin, LoginRequiredMixin, FormView):
    required_capability = Capability.HEARINGS_MANAGE
    form_class = HearingScheduleForm
    template_name = "hearings/hearing_form.html"

    def dispatch(self, request, *args, **kwargs):
        self.case_obj = None
        if request.user.is_authenticated:
            case_pk = request.GET.get("case") or request.POST.get("case")
            if case_pk:
                self.case_obj = _get_case(request.user, case_pk)
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "user": self.request.user, "case": self.case_obj}

    def form_valid(self, form):
        cd = form.cleaned_data
        case = self.case_obj or cd["case"]
        hearing = services.schedule_hearing(
            actor=self.request.user,
            case=case,
            scheduled_at=services.combine(cd["date"], cd.get("time")),
            hearing_type=cd["hearing_type"],
            court=cd.get("court"),
            lawyer=cd.get("lawyer"),
            room=cd.get("room", ""),
            notes=cd.get("notes", ""),
            request=self.request,
        )
        messages.success(self.request, _("تمت جدولة الجلسة."))
        return redirect("hearings:detail", pk=hearing.pk)

    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), "is_create": True, "case": self.case_obj}


class _HearingActionMixin(CapabilityRequiredMixin, LoginRequiredMixin, FormView):
    required_capability = Capability.HEARINGS_MANAGE

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            self.hearing = _get_hearing(request.user, kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    def _guard_open(self):
        if not self.hearing.is_open:
            messages.error(self.request, _("لا يمكن تنفيذ هذا الإجراء على جلسة مغلقة."))
            return redirect("hearings:detail", pk=self.hearing.pk)
        return None

    def get(self, request, *args, **kwargs):
        blocked = self._guard_open()
        return blocked or super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        blocked = self._guard_open()
        return blocked or super().post(request, *args, **kwargs)

    def get_success_url(self):
        return reverse("hearings:detail", args=[self.hearing.pk])

    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), "hearing": self.hearing}


class HearingUpdateView(_HearingActionMixin):
    form_class = HearingUpdateForm
    template_name = "hearings/hearing_form.html"

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "instance": self.hearing}

    def form_valid(self, form):
        cd = form.cleaned_data
        services.update_hearing(
            actor=self.request.user,
            hearing=self.hearing,
            data={
                "scheduled_at": services.combine(cd["date"], cd.get("time")),
                "hearing_type": cd["hearing_type"],
                "court": cd.get("court"),
                "lawyer": cd.get("lawyer"),
                "room": cd.get("room", ""),
                "notes": cd.get("notes", ""),
            },
            request=self.request,
        )
        messages.success(self.request, _("تم حفظ التعديلات."))
        return redirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), "is_create": False}


class HearingCompleteView(_HearingActionMixin):
    form_class = HearingCompleteForm
    template_name = "hearings/hearing_complete.html"

    def form_valid(self, form):
        cd = form.cleaned_data
        services.complete_hearing(
            actor=self.request.user,
            hearing=self.hearing,
            result=cd.get("result", ""),
            notes=cd.get("notes", ""),
            next_action=cd.get("next_action", ""),
            next_hearing_date=cd.get("next_hearing_date"),
            next_hearing_time=cd.get("next_hearing_time"),
            request=self.request,
        )
        messages.success(self.request, _("تم تسجيل نتيجة الجلسة."))
        return redirect(self.get_success_url())


class HearingPostponeView(_HearingActionMixin):
    form_class = HearingPostponeForm
    template_name = "hearings/hearing_postpone.html"

    def form_valid(self, form):
        cd = form.cleaned_data
        services.postpone_hearing(
            actor=self.request.user,
            hearing=self.hearing,
            next_hearing_date=cd["next_hearing_date"],
            next_hearing_time=cd.get("next_hearing_time"),
            next_action=cd.get("next_action", ""),
            reason=cd.get("reason", ""),
            request=self.request,
        )
        messages.success(self.request, _("تم تأجيل الجلسة وإنشاء الجلسة القادمة."))
        return redirect(self.get_success_url())


@require_POST
@require_capability(Capability.HEARINGS_MANAGE)
def hearing_cancel(request, pk):
    hearing = _get_hearing(request.user, pk)
    if not hearing.is_open:
        messages.error(request, _("الجلسة مغلقة بالفعل."))
        return redirect("hearings:detail", pk=pk)
    form = HearingCancelForm(request.POST)
    reason = form.cleaned_data.get("reason", "") if form.is_valid() else ""
    services.cancel_hearing(actor=request.user, hearing=hearing, reason=reason, request=request)
    messages.success(request, _("تم إلغاء الجلسة."))
    return redirect("hearings:detail", pk=pk)
