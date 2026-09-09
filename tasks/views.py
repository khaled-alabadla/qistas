"""Task + deadline list, detail, CRUD and status actions (spec §31–32, §48).

Every staff member may view tasks and deadlines (``tasks.view``); creating,
editing and status changes require ``tasks.manage``. Writes go through
``tasks.services`` so the audit trail + case timeline stay consistent. Tasks
soft-delete; deadlines are cancelled, never deleted (docs/adr/0022).
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
from core.forms import with_current_choice
from core.permissions.capabilities import Capability, can
from core.permissions.decorators import require_capability
from core.permissions.mixins import CapabilityRequiredMixin
from core.querysets import assert_scoped
from tasks import services
from tasks.forms import (
    DeadlineFilterForm,
    DeadlineForm,
    DeadlineStatusForm,
    TaskFilterForm,
    TaskForm,
    TaskStatusForm,
)
from tasks.models import Deadline, DeadlineStatus, Task, TaskStatus
from tasks.selectors import deadline_list, task_list

PAGE_SIZE = 25


def _get_task(user, pk) -> Task:
    qs = (
        Task.objects.for_user(user)
        .alive()
        .select_related("assigned_to", "case", "client", "created_by", "updated_by")
    )
    assert_scoped(qs)
    return get_object_or_404(qs, pk=pk)


def _get_deadline(user, pk) -> Deadline:
    qs = Deadline.objects.for_user(user).select_related(
        "case", "client", "created_by", "updated_by"
    )
    assert_scoped(qs)
    return get_object_or_404(qs, pk=pk)


def _page(request, object_list):
    paginator = Paginator(object_list, PAGE_SIZE)
    page = paginator.get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)
    qs = params.urlencode()
    return page, paginator.count, (f"{qs}&" if qs else "")


# ── Tasks ──────────────────────────────────────────────────
class TaskListView(CapabilityRequiredMixin, LoginRequiredMixin, ListView):
    required_capability = Capability.TASKS_VIEW
    template_name = "tasks/task_list.html"
    context_object_name = "tasks"

    def get_queryset(self):
        self.filter_form = TaskFilterForm(self.request.GET or None)
        self.filter_form.is_valid()
        data = self.filter_form.cleaned_data if self.filter_form.is_bound else {}
        assignee_id = getattr(data.get("assignee"), "pk", "") or ""
        if data.get("mine"):
            assignee_id = self.request.user.pk
        qs = task_list(
            user=self.request.user,
            query=data.get("q", ""),
            status=data.get("status", ""),
            priority=data.get("priority", ""),
            assignee_id=assignee_id,
            overdue_only=bool(data.get("overdue")),
        )
        assert_scoped(qs)
        return qs

    def get_context_data(self, **kwargs):
        page, count, querystring = _page(self.request, self.object_list)
        return {
            **super().get_context_data(object_list=page.object_list, **kwargs),
            "filter_form": self.filter_form,
            "page_obj": page,
            "tasks": page.object_list,
            "total_count": count,
            "querystring": querystring,
            "can_manage": can(self.request.user, Capability.TASKS_MANAGE),
        }


class TaskDetailView(CapabilityRequiredMixin, LoginRequiredMixin, DetailView):
    required_capability = Capability.TASKS_VIEW
    template_name = "tasks/task_detail.html"
    context_object_name = "task"

    def get_object(self, queryset=None):
        return _get_task(self.request.user, self.kwargs["pk"])

    def get_context_data(self, **kwargs):
        return {
            **super().get_context_data(**kwargs),
            "can_manage": can(self.request.user, Capability.TASKS_MANAGE),
            "status_form": TaskStatusForm(initial={"status": self.object.status}),
        }


def _widen_case_field(request, form) -> None:
    """If ``?case=`` names a case the user can see (even a closed one), keep it a
    valid choice on the create form even though the picker lists only open cases."""
    case_id = request.GET.get("case")
    if not str(case_id).isdigit():
        return
    scoped = Case.objects.for_user(request.user)
    assert_scoped(scoped)
    if scoped.filter(pk=case_id).exists():
        form.fields["case"].queryset = with_current_choice(form.fields["case"].queryset, case_id)


class _TaskFormMixin(CapabilityRequiredMixin, LoginRequiredMixin, FormView):
    required_capability = Capability.TASKS_MANAGE
    form_class = TaskForm
    template_name = "tasks/task_form.html"

    def get_success_url(self):
        return reverse("tasks:detail", args=[self.object.pk])


class TaskCreateView(_TaskFormMixin):
    def get_initial(self):
        initial = {}
        case_id = self.request.GET.get("case")
        client_id = self.request.GET.get("client")
        if str(case_id).isdigit():
            initial["case"] = case_id
        if str(client_id).isdigit():
            initial["client"] = client_id
        return initial

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        _widen_case_field(self.request, form)
        return form

    def form_valid(self, form):
        self.object = services.create_task(
            actor=self.request.user, data=form.cleaned_data, request=self.request
        )
        messages.success(self.request, _("تمت إضافة المهمة."))
        return redirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), "is_create": True}


class TaskUpdateView(_TaskFormMixin):
    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            self.task_obj = _get_task(request.user, kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "instance": self.task_obj}

    def form_valid(self, form):
        self.object = services.update_task(
            actor=self.request.user,
            task=self.task_obj,
            data=form.cleaned_data,
            request=self.request,
        )
        messages.success(self.request, _("تم حفظ التعديلات."))
        return redirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), "is_create": False, "task": self.task_obj}


@require_POST
@require_capability(Capability.TASKS_MANAGE)
def task_status(request, pk):
    task = _get_task(request.user, pk)
    form = TaskStatusForm(request.POST)
    if form.is_valid() and form.cleaned_data["status"] in TaskStatus.values:
        services.change_task_status(
            actor=request.user, task=task, new_status=form.cleaned_data["status"], request=request
        )
        messages.success(request, _("تم تحديث حالة المهمة."))
    else:
        messages.error(request, _("حالة غير صالحة."))
    return redirect("tasks:detail", pk=pk)


@require_POST
@require_capability(Capability.TASKS_MANAGE)
def task_delete(request, pk):
    task = _get_task(request.user, pk)
    services.delete_task(actor=request.user, task=task, request=request)
    messages.success(request, _("تم حذف المهمة."))
    return redirect("tasks:list")


# ── Deadlines ──────────────────────────────────────────────
class DeadlineListView(CapabilityRequiredMixin, LoginRequiredMixin, ListView):
    required_capability = Capability.TASKS_VIEW
    template_name = "tasks/deadline_list.html"
    context_object_name = "deadlines"

    def get_queryset(self):
        self.filter_form = DeadlineFilterForm(self.request.GET or None)
        self.filter_form.is_valid()
        data = self.filter_form.cleaned_data if self.filter_form.is_bound else {}
        qs = deadline_list(
            user=self.request.user,
            query=data.get("q", ""),
            status=data.get("status", ""),
            overdue_only=bool(data.get("overdue")),
        )
        assert_scoped(qs)
        return qs

    def get_context_data(self, **kwargs):
        page, count, querystring = _page(self.request, self.object_list)
        return {
            **super().get_context_data(object_list=page.object_list, **kwargs),
            "filter_form": self.filter_form,
            "page_obj": page,
            "deadlines": page.object_list,
            "total_count": count,
            "querystring": querystring,
            "can_manage": can(self.request.user, Capability.TASKS_MANAGE),
        }


class DeadlineDetailView(CapabilityRequiredMixin, LoginRequiredMixin, DetailView):
    required_capability = Capability.TASKS_VIEW
    template_name = "tasks/deadline_detail.html"
    context_object_name = "deadline"

    def get_object(self, queryset=None):
        return _get_deadline(self.request.user, self.kwargs["pk"])

    def get_context_data(self, **kwargs):
        return {
            **super().get_context_data(**kwargs),
            "can_manage": can(self.request.user, Capability.TASKS_MANAGE),
            "status_form": DeadlineStatusForm(initial={"status": self.object.status}),
        }


class _DeadlineFormMixin(CapabilityRequiredMixin, LoginRequiredMixin, FormView):
    required_capability = Capability.TASKS_MANAGE
    form_class = DeadlineForm
    template_name = "tasks/deadline_form.html"

    def get_success_url(self):
        return reverse("tasks:deadline_detail", args=[self.object.pk])


class DeadlineCreateView(_DeadlineFormMixin):
    def get_initial(self):
        initial = {}
        case_id = self.request.GET.get("case")
        if str(case_id).isdigit():
            initial["case"] = case_id
        return initial

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        _widen_case_field(self.request, form)
        return form

    def form_valid(self, form):
        self.object = services.create_deadline(
            actor=self.request.user, data=form.cleaned_data, request=self.request
        )
        messages.success(self.request, _("تمت إضافة الموعد النهائي."))
        return redirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), "is_create": True}


class DeadlineUpdateView(_DeadlineFormMixin):
    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            self.deadline_obj = _get_deadline(request.user, kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "instance": self.deadline_obj}

    def form_valid(self, form):
        self.object = services.update_deadline(
            actor=self.request.user,
            deadline=self.deadline_obj,
            data=form.cleaned_data,
            request=self.request,
        )
        messages.success(self.request, _("تم حفظ التعديلات."))
        return redirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        return {
            **super().get_context_data(**kwargs),
            "is_create": False,
            "deadline": self.deadline_obj,
        }


@require_POST
@require_capability(Capability.TASKS_MANAGE)
def deadline_status(request, pk):
    deadline = _get_deadline(request.user, pk)
    form = DeadlineStatusForm(request.POST)
    if form.is_valid() and form.cleaned_data["status"] in DeadlineStatus.values:
        services.change_deadline_status(
            actor=request.user,
            deadline=deadline,
            new_status=form.cleaned_data["status"],
            request=request,
        )
        messages.success(request, _("تم تحديث حالة الموعد النهائي."))
    else:
        messages.error(request, _("حالة غير صالحة."))
    return redirect("tasks:deadline_detail", pk=pk)
