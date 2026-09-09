"""Hearing forms — schedule, edit, complete, postpone, cancel, filter.

Spec §29 lists ``date`` + ``time`` separately; the forms keep that split (a
required date, an optional time defaulting to 09:00) and the service recombines
them into the timezone-aware ``scheduled_at`` (docs/adr/0028).
"""

from __future__ import annotations

from django import forms
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _

from cases.models import Case, CaseStatus
from core.forms import with_current_choice as _with_current
from courts.models import Court
from hearings.models import Hearing, HearingStatus, HearingType

User = get_user_model()

LAWYER_GROUPS = ("office_manager", "lawyer", "paralegal", "admin_clerk")


def _lawyer_queryset():
    return User.objects.filter(is_active=True, groups__name__in=LAWYER_GROUPS).distinct()


def _reject_past(value):
    """A *next* hearing date can never be in the past."""
    if value is not None:
        from django.utils import timezone

        if value < timezone.localdate():
            raise forms.ValidationError(_("لا يمكن أن يكون التاريخ في الماضي."))
    return value


class _DateInput(forms.DateInput):
    input_type = "date"


class _TimeInput(forms.TimeInput):
    input_type = "time"


class _HearingDetailsMixin(forms.Form):
    """Shared date/time/type/court/lawyer/room/notes block."""

    date = forms.DateField(label=_("التاريخ"), widget=_DateInput())
    time = forms.TimeField(label=_("الوقت"), required=False, widget=_TimeInput())
    hearing_type = forms.ChoiceField(label=_("نوع الجلسة"), choices=HearingType.choices)
    court = forms.ModelChoiceField(
        label=_("المحكمة"),
        queryset=Court.objects.filter(is_active=True),
        required=False,
        empty_label=_("— اختر —"),
    )
    lawyer = forms.ModelChoiceField(
        label=_("المحامي الحاضر"),
        queryset=_lawyer_queryset(),
        required=False,
        empty_label=_("— اختر —"),
    )
    room = forms.CharField(label=_("القاعة"), max_length=60, required=False)
    notes = forms.CharField(
        label=_("ملاحظات"), required=False, widget=forms.Textarea(attrs={"rows": 3})
    )


class HearingScheduleForm(_HearingDetailsMixin):
    case = forms.ModelChoiceField(label=_("القضية"), queryset=Case.objects.none())

    field_order = ["case", "date", "time", "hearing_type", "court", "lawyer", "room", "notes"]

    def __init__(self, *args, user=None, case=None, **kwargs):
        super().__init__(*args, **kwargs)
        qs = Case.objects.for_user(user) if user else Case.objects.none()
        self.fields["case"].queryset = qs.exclude(
            status__in=[CaseStatus.CONCLUDED, CaseStatus.CLOSED]
        ).select_related("client")
        if case is not None:
            self.fields["case"].initial = case.pk
            self.fields["case"].disabled = True
            self.fields["case"].queryset = Case.objects.filter(pk=case.pk)


class HearingUpdateForm(_HearingDetailsMixin):
    """Edit a still-scheduled hearing."""

    def __init__(self, *args, instance: Hearing, **kwargs):
        self.instance = instance
        super().__init__(*args, **kwargs)
        self.fields["court"].queryset = _with_current(
            Court.objects.filter(is_active=True), instance.court_id
        )
        self.fields["lawyer"].queryset = _with_current(_lawyer_queryset(), instance.lawyer_id)
        if not self.is_bound:
            from django.utils import timezone

            local = timezone.localtime(instance.scheduled_at)
            self.fields["date"].initial = local.date()
            self.fields["time"].initial = local.time().replace(second=0, microsecond=0)
            self.fields["hearing_type"].initial = instance.hearing_type
            self.fields["court"].initial = instance.court_id
            self.fields["lawyer"].initial = instance.lawyer_id
            self.fields["room"].initial = instance.room
            self.fields["notes"].initial = instance.notes


class HearingCompleteForm(forms.Form):
    result = forms.CharField(
        label=_("النتيجة"), required=False, widget=forms.Textarea(attrs={"rows": 3})
    )
    notes = forms.CharField(
        label=_("ملاحظات"), required=False, widget=forms.Textarea(attrs={"rows": 2})
    )
    next_action = forms.CharField(label=_("الإجراء التالي"), max_length=250, required=False)
    next_hearing_date = forms.DateField(
        label=_("تاريخ الجلسة القادمة"), required=False, widget=_DateInput()
    )
    next_hearing_time = forms.TimeField(
        label=_("وقت الجلسة القادمة"), required=False, widget=_TimeInput()
    )

    def clean_next_hearing_date(self):
        return _reject_past(self.cleaned_data.get("next_hearing_date"))

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("next_hearing_time") and not cleaned.get("next_hearing_date"):
            self.add_error("next_hearing_date", _("حدّد تاريخ الجلسة القادمة."))
        return cleaned


class HearingPostponeForm(forms.Form):
    next_hearing_date = forms.DateField(label=_("تاريخ الجلسة القادمة"), widget=_DateInput())
    next_hearing_time = forms.TimeField(
        label=_("وقت الجلسة القادمة"), required=False, widget=_TimeInput()
    )
    next_action = forms.CharField(label=_("الإجراء التالي"), max_length=250, required=False)
    reason = forms.CharField(
        label=_("سبب التأجيل"), required=False, widget=forms.Textarea(attrs={"rows": 2})
    )

    def clean_next_hearing_date(self):
        return _reject_past(self.cleaned_data.get("next_hearing_date"))


class HearingCancelForm(forms.Form):
    reason = forms.CharField(
        label=_("سبب الإلغاء"), required=False, widget=forms.Textarea(attrs={"rows": 2})
    )


class HearingFilterForm(forms.Form):
    q = forms.CharField(
        label=_("بحث"),
        required=False,
        widget=forms.TextInput(
            attrs={"placeholder": _("رقم القضية، العنوان، المحكمة…"), "type": "search"}
        ),
    )
    when = forms.ChoiceField(
        label=_("الفترة"),
        required=False,
        choices=[
            ("upcoming", _("القادمة")),
            ("past", _("السابقة")),
            ("all", _("الكل")),
        ],
    )
    status = forms.ChoiceField(
        label=_("الحالة"),
        required=False,
        choices=[("", _("كل الحالات")), *HearingStatus.choices],
    )
    hearing_type = forms.ChoiceField(
        label=_("النوع"),
        required=False,
        choices=[("", _("كل الأنواع")), *HearingType.choices],
    )
    court = forms.ModelChoiceField(
        label=_("المحكمة"),
        required=False,
        queryset=Court.objects.all(),
        empty_label=_("كل المحاكم"),
    )
