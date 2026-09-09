"""Task + deadline forms — create/edit, filters, status actions."""

from __future__ import annotations

from django import forms
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _

from cases.models import Case, CaseStatus
from clients.models import Client, ClientStatus
from core.forms import with_current_choice
from tasks.models import (
    Deadline,
    DeadlineStatus,
    Task,
    TaskPriority,
    TaskStatus,
)

User = get_user_model()

STAFF_GROUPS = ("office_manager", "lawyer", "paralegal", "admin_clerk", "finance_clerk")


class _DateInput(forms.DateInput):
    input_type = "date"


def _staff_queryset():
    return User.objects.filter(is_active=True, groups__name__in=STAFF_GROUPS).distinct()


def _open_cases():
    return Case.objects.exclude(
        status__in=[CaseStatus.CONCLUDED, CaseStatus.CLOSED]
    ).select_related("client")


def _active_clients():
    return Client.objects.exclude(status=ClientStatus.ARCHIVED)


class TaskForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = ["title", "description", "assigned_to", "case", "client", "priority", "due_date"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "due_date": _DateInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        inst = self.instance if self.instance and self.instance.pk else None
        self.fields["assigned_to"].queryset = with_current_choice(
            _staff_queryset(), getattr(inst, "assigned_to_id", None)
        )
        self.fields["case"].queryset = with_current_choice(
            _open_cases(), getattr(inst, "case_id", None)
        )
        self.fields["client"].queryset = with_current_choice(
            _active_clients(), getattr(inst, "client_id", None)
        )
        for name in ("description", "assigned_to", "case", "client", "due_date"):
            self.fields[name].required = False


class DeadlineForm(forms.ModelForm):
    class Meta:
        model = Deadline
        fields = ["title", "description", "case", "client", "due_date"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "due_date": _DateInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        inst = self.instance if self.instance and self.instance.pk else None
        self.fields["case"].queryset = with_current_choice(
            _open_cases(), getattr(inst, "case_id", None)
        )
        self.fields["client"].queryset = with_current_choice(
            _active_clients(), getattr(inst, "client_id", None)
        )
        for name in ("description", "case", "client"):
            self.fields[name].required = False


class TaskFilterForm(forms.Form):
    q = forms.CharField(
        label=_("بحث"),
        required=False,
        widget=forms.TextInput(attrs={"placeholder": _("عنوان المهمة…"), "type": "search"}),
    )
    status = forms.ChoiceField(
        label=_("الحالة"),
        required=False,
        choices=[("", _("المفتوحة")), *TaskStatus.choices],
    )
    priority = forms.ChoiceField(
        label=_("الأولوية"),
        required=False,
        choices=[("", _("كل الأولويات")), *TaskPriority.choices],
    )
    assignee = forms.ModelChoiceField(
        label=_("المُسند إليه"),
        required=False,
        queryset=_staff_queryset(),
        empty_label=_("الجميع"),
    )
    overdue = forms.BooleanField(label=_("المتأخرة فقط"), required=False)
    mine = forms.BooleanField(label=_("مهامي فقط"), required=False)


class DeadlineFilterForm(forms.Form):
    q = forms.CharField(
        label=_("بحث"),
        required=False,
        widget=forms.TextInput(attrs={"placeholder": _("عنوان الموعد…"), "type": "search"}),
    )
    status = forms.ChoiceField(
        label=_("الحالة"),
        required=False,
        choices=[("", _("المفتوحة")), *DeadlineStatus.choices],
    )
    overdue = forms.BooleanField(label=_("المتأخرة فقط"), required=False)


class TaskStatusForm(forms.Form):
    status = forms.ChoiceField(label=_("الحالة الجديدة"), choices=TaskStatus.choices)


class DeadlineStatusForm(forms.Form):
    status = forms.ChoiceField(label=_("الحالة الجديدة"), choices=DeadlineStatus.choices)
