"""Court directory + CRUD (spec §28, docs/adr/0028).

Every staff member may view courts (``courts.view``); only the office manager
edits them (``courts.manage``). A court is deactivated, never deleted
(docs/adr/0022) — historical cases and hearings still reference it.
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

from core.permissions.capabilities import Capability, can
from core.permissions.decorators import require_capability
from core.permissions.mixins import CapabilityRequiredMixin
from core.querysets import assert_scoped
from courts import services
from courts.forms import CourtFilterForm, CourtForm
from courts.models import Court
from courts.selectors import court_list

PAGE_SIZE = 25


def _get_court(user, pk) -> Court:
    qs = Court.objects.for_user(user)
    assert_scoped(qs)
    return get_object_or_404(qs, pk=pk)


class CourtListView(CapabilityRequiredMixin, LoginRequiredMixin, ListView):
    required_capability = Capability.COURTS_VIEW
    template_name = "courts/court_list.html"
    context_object_name = "courts"

    def get_queryset(self):
        self.filter_form = CourtFilterForm(self.request.GET or None)
        self.filter_form.is_valid()
        data = self.filter_form.cleaned_data if self.filter_form.is_bound else {}
        qs = court_list(
            user=self.request.user,
            query=data.get("q", ""),
            type=data.get("type", ""),
            include_inactive=data.get("include_inactive", False),
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
            "courts": page.object_list,
            "total_count": paginator.count,
            "querystring": f"{querystring}&" if querystring else "",
            "can_manage": can(self.request.user, Capability.COURTS_MANAGE),
        }


class CourtDetailView(CapabilityRequiredMixin, LoginRequiredMixin, DetailView):
    required_capability = Capability.COURTS_VIEW
    template_name = "courts/court_detail.html"
    context_object_name = "court"

    def get_object(self, queryset=None):
        return _get_court(self.request.user, self.kwargs["pk"])

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        court = self.object
        ctx.update(
            {
                "can_manage": can(self.request.user, Capability.COURTS_MANAGE),
                "case_count": court.cases.count(),
                "hearing_count": court.hearings.count(),
            }
        )
        return ctx


class _CourtFormMixin(CapabilityRequiredMixin, LoginRequiredMixin, FormView):
    required_capability = Capability.COURTS_MANAGE
    form_class = CourtForm
    template_name = "courts/court_form.html"

    def get_success_url(self):
        return reverse("courts:detail", args=[self.object.pk])


class CourtCreateView(_CourtFormMixin):
    def form_valid(self, form):
        self.object = services.create_court(
            actor=self.request.user, data=form.cleaned_data, request=self.request
        )
        messages.success(self.request, _("تمت إضافة المحكمة."))
        return redirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), "is_create": True}


class CourtUpdateView(_CourtFormMixin):
    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            self.court_obj = _get_court(request.user, kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "instance": self.court_obj}

    def form_valid(self, form):
        self.object = services.update_court(
            actor=self.request.user,
            court=self.court_obj,
            data=form.cleaned_data,
            request=self.request,
        )
        messages.success(self.request, _("تم حفظ التعديلات."))
        return redirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), "is_create": False, "court": self.court_obj}


@require_POST
@require_capability(Capability.COURTS_MANAGE)
def court_set_active(request, pk):
    court = _get_court(request.user, pk)
    is_active = request.POST.get("is_active") == "1"
    services.set_active(actor=request.user, court=court, is_active=is_active, request=request)
    messages.success(request, _("تم تفعيل المحكمة.") if is_active else _("تم إلغاء تفعيل المحكمة."))
    return redirect("courts:detail", pk=pk)
