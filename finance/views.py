"""
Finance views — fee agreements, invoices (+ line items, issue, cancel, credit
note), payments (+ reversal), expenses (spec §38–42, §21, §97, §98).

`finance.view` gates every list + detail; `finance.manage` gates every mutation.
Views are thin: **no money math, no transactional logic** — everything goes
through `finance.services` (row-locked where §40 requires it). Object access is
always through a `for_user()`-scoped queryset + `get_object_or_404`.
"""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST
from django.views.generic import DetailView, FormView, ListView

from cases.models import Case
from clients.models import Client
from core.permissions.capabilities import Capability, can
from core.permissions.decorators import require_capability
from core.permissions.mixins import CapabilityRequiredMixin
from core.querysets import assert_scoped
from finance import services
from finance.forms import (
    CreditNoteForm,
    ExpenseFilterForm,
    ExpenseForm,
    FeeAgreementFilterForm,
    FeeAgreementForm,
    FeeAgreementStatusForm,
    InvoiceFilterForm,
    InvoiceForm,
    IssueInvoiceForm,
    LineItemForm,
    PaymentFilterForm,
    PaymentForm,
    PaymentReversalForm,
)
from finance.models import (
    Expense,
    FeeAgreement,
    Invoice,
    Payment,
)
from finance.selectors import (
    expense_list,
    fee_agreement_list,
    invoice_detail_queryset,
    invoice_list,
    payment_list,
)

PAGE_SIZE = 25
V = Capability.FINANCE_VIEW
M = Capability.FINANCE_MANAGE


def _page(request, object_list):
    paginator = Paginator(object_list, PAGE_SIZE)
    page = paginator.get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)
    qs = params.urlencode()
    return page, paginator.count, (f"{qs}&" if qs else "")


def _scoped_fee_agreement(user, pk) -> FeeAgreement:
    qs = FeeAgreement.objects.for_user(user).select_related(
        "case", "case__client", "created_by", "updated_by"
    )
    assert_scoped(qs)
    return get_object_or_404(qs, pk=pk)


def _scoped_invoice(user, pk) -> Invoice:
    qs = invoice_detail_queryset(user)
    assert_scoped(qs)
    return get_object_or_404(qs, pk=pk)


def _scoped_payment(user, pk) -> Payment:
    qs = (
        Payment.objects.for_user(user)
        .select_related("invoice", "invoice__client", "invoice__case", "created_by")
        .prefetch_related("reversals")
    )
    assert_scoped(qs)
    return get_object_or_404(qs, pk=pk)


def _scoped_expense(user, pk) -> Expense:
    qs = Expense.objects.for_user(user).select_related("case", "client", "created_by", "updated_by")
    assert_scoped(qs)
    return get_object_or_404(qs, pk=pk)


# ═══ Fee agreements ═══════════════════════════════════════
class FeeAgreementListView(CapabilityRequiredMixin, LoginRequiredMixin, ListView):
    required_capability = V
    template_name = "finance/fee_agreement_list.html"
    context_object_name = "fee_agreements"

    def get_queryset(self):
        self.filter_form = FeeAgreementFilterForm(self.request.GET or None)
        self.filter_form.is_valid()
        data = self.filter_form.cleaned_data if self.filter_form.is_bound else {}
        qs = fee_agreement_list(
            user=self.request.user,
            query=data.get("q", ""),
            status=data.get("status", ""),
            fee_type=data.get("fee_type", ""),
            case_id=self.request.GET.get("case", ""),
        )
        assert_scoped(qs)
        return qs

    def get_context_data(self, **kwargs):
        page, count, querystring = _page(self.request, self.object_list)
        return {
            **super().get_context_data(object_list=page.object_list, **kwargs),
            "filter_form": self.filter_form,
            "page_obj": page,
            "fee_agreements": page.object_list,
            "total_count": count,
            "querystring": querystring,
            "can_manage": can(self.request.user, M),
        }


class FeeAgreementDetailView(CapabilityRequiredMixin, LoginRequiredMixin, DetailView):
    required_capability = V
    template_name = "finance/fee_agreement_detail.html"
    context_object_name = "fee_agreement"

    def get_object(self, queryset=None):
        return _scoped_fee_agreement(self.request.user, self.kwargs["pk"])

    def get_context_data(self, **kwargs):
        return {
            **super().get_context_data(**kwargs),
            "can_manage": can(self.request.user, M),
            "status_form": FeeAgreementStatusForm(initial={"status": self.object.status}),
        }


class _FeeAgreementFormMixin(CapabilityRequiredMixin, LoginRequiredMixin, FormView):
    required_capability = M
    form_class = FeeAgreementForm
    template_name = "finance/fee_agreement_form.html"

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "user": self.request.user}

    def get_success_url(self):
        return reverse("finance:fee_agreement_detail", args=[self.object.pk])


class FeeAgreementCreateView(_FeeAgreementFormMixin):
    def get_initial(self):
        case_id = self.request.GET.get("case")
        if (
            str(case_id).isdigit()
            and Case.objects.for_user(self.request.user).filter(pk=case_id).exists()
        ):
            return {"case": case_id}
        return {}

    def form_valid(self, form):
        self.object = services.create_fee_agreement(
            actor=self.request.user, data=form.cleaned_data, request=self.request
        )
        messages.success(self.request, _("تمت إضافة اتفاقية الأتعاب."))
        return redirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), "is_create": True}


class FeeAgreementUpdateView(_FeeAgreementFormMixin):
    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            self.obj = _scoped_fee_agreement(request.user, kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "instance": self.obj}

    def form_valid(self, form):
        try:
            self.object = services.update_fee_agreement(
                actor=self.request.user,
                fee_agreement=self.obj,
                data=form.cleaned_data,
                request=self.request,
            )
        except ValidationError as exc:
            form.add_error(None, exc.messages)
            return self.form_invalid(form)
        messages.success(self.request, _("تم حفظ التعديلات."))
        return redirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), "is_create": False, "fee_agreement": self.obj}


@require_POST
@require_capability(M)
def fee_agreement_status(request, pk):
    fa = _scoped_fee_agreement(request.user, pk)
    form = FeeAgreementStatusForm(request.POST)
    if form.is_valid():
        try:
            services.change_fee_agreement_status(
                actor=request.user,
                fee_agreement=fa,
                new_status=form.cleaned_data["status"],
                request=request,
            )
            messages.success(request, _("تم تحديث حالة اتفاقية الأتعاب."))
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
    else:
        messages.error(request, _("حالة غير صالحة."))
    return redirect("finance:fee_agreement_detail", pk=pk)


# ═══ Invoices ═════════════════════════════════════════════
class InvoiceListView(CapabilityRequiredMixin, LoginRequiredMixin, ListView):
    required_capability = V
    template_name = "finance/invoice_list.html"
    context_object_name = "invoices"

    def get_queryset(self):
        self.filter_form = InvoiceFilterForm(self.request.GET or None)
        self.filter_form.is_valid()
        data = self.filter_form.cleaned_data if self.filter_form.is_bound else {}
        qs = invoice_list(
            user=self.request.user,
            query=data.get("q", ""),
            status=data.get("status", ""),
            client_id=self.request.GET.get("client", ""),
            case_id=self.request.GET.get("case", ""),
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
            "invoices": page.object_list,
            "total_count": count,
            "querystring": querystring,
            "can_manage": can(self.request.user, M),
        }


class InvoiceDetailView(CapabilityRequiredMixin, LoginRequiredMixin, DetailView):
    required_capability = V
    template_name = "finance/invoice_detail.html"
    context_object_name = "invoice"

    def get_object(self, queryset=None):
        return _scoped_invoice(self.request.user, self.kwargs["pk"])

    def get_context_data(self, **kwargs):
        inv = self.object
        return {
            **super().get_context_data(**kwargs),
            "can_manage": can(self.request.user, M),
            "line_items": list(inv.line_items.all()),
            "payments": list(inv.payments.all()),
            "credit_notes": list(inv.credit_notes.all()),
            "line_form": LineItemForm(),
            "payment_form": PaymentForm(),
            "issue_form": IssueInvoiceForm(),
            "credit_note_form": CreditNoteForm(),
        }


class _InvoiceFormMixin(CapabilityRequiredMixin, LoginRequiredMixin, FormView):
    required_capability = M
    form_class = InvoiceForm
    template_name = "finance/invoice_form.html"

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "user": self.request.user}

    def get_success_url(self):
        return reverse("finance:invoice_detail", args=[self.object.pk])


class InvoiceCreateView(_InvoiceFormMixin):
    def get_initial(self):
        initial = {}
        user = self.request.user
        for key, model in (("case", Case), ("client", Client)):
            val = self.request.GET.get(key)
            if str(val).isdigit() and model.objects.for_user(user).filter(pk=val).exists():
                initial[key] = val
        return initial

    def form_valid(self, form):
        self.object = services.create_invoice(
            actor=self.request.user, data=form.cleaned_data, request=self.request
        )
        messages.success(self.request, _("أُنشئت مسودة الفاتورة. أضف البنود ثم أصدرها."))
        return redirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), "is_create": True}


class InvoiceUpdateView(_InvoiceFormMixin):
    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            self.invoice_obj = _scoped_invoice(request.user, kwargs["pk"])
            if not self.invoice_obj.is_draft:
                messages.error(request, _("لا يمكن تعديل فاتورة صادرة."))
                return redirect("finance:invoice_detail", pk=self.invoice_obj.pk)
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "instance": self.invoice_obj}

    def form_valid(self, form):
        try:
            self.object = services.update_invoice(
                actor=self.request.user,
                invoice=self.invoice_obj,
                data=form.cleaned_data,
                request=self.request,
            )
        except ValidationError as exc:
            form.add_error(None, exc.messages)
            return self.form_invalid(form)
        messages.success(self.request, _("تم حفظ التعديلات."))
        return redirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        return {
            **super().get_context_data(**kwargs),
            "is_create": False,
            "invoice": self.invoice_obj,
        }


@require_POST
@require_capability(M)
def invoice_line_add(request, pk):
    invoice = _scoped_invoice(request.user, pk)
    form = LineItemForm(request.POST)
    if form.is_valid():
        try:
            services.add_line_item(
                actor=request.user, invoice=invoice, data=form.cleaned_data, request=request
            )
            messages.success(request, _("أُضيف البند."))
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
    else:
        messages.error(request, _("تعذّر إضافة البند — تحقّق من القيم."))
    return redirect("finance:invoice_detail", pk=pk)


@require_POST
@require_capability(M)
def invoice_line_remove(request, pk, line_pk):
    invoice = _scoped_invoice(request.user, pk)
    line = get_object_or_404(invoice.line_items, pk=line_pk)
    try:
        services.remove_line_item(actor=request.user, invoice=invoice, line=line, request=request)
        messages.success(request, _("حُذف البند."))
    except ValidationError as exc:
        messages.error(request, exc.messages[0])
    return redirect("finance:invoice_detail", pk=pk)


@require_POST
@require_capability(M)
def invoice_issue(request, pk):
    invoice = _scoped_invoice(request.user, pk)
    form = IssueInvoiceForm(request.POST)
    if not form.is_valid():
        messages.error(request, _("تاريخ الإصدار غير صالح."))
        return redirect("finance:invoice_detail", pk=pk)
    try:
        services.issue_invoice(
            actor=request.user,
            invoice=invoice,
            issue_date=form.cleaned_data.get("issue_date"),
            request=request,
        )
        messages.success(request, _("صدرت الفاتورة."))
    except ValidationError as exc:
        messages.error(request, exc.messages[0])
    return redirect("finance:invoice_detail", pk=pk)


@require_POST
@require_capability(M)
def invoice_cancel(request, pk):
    invoice = _scoped_invoice(request.user, pk)
    try:
        services.cancel_invoice(actor=request.user, invoice=invoice, request=request)
        messages.success(request, _("أُلغيت المسودة."))
    except ValidationError as exc:
        messages.error(request, exc.messages[0])
    return redirect("finance:invoice_detail", pk=pk)


@require_POST
@require_capability(M)
def payment_create(request, pk):
    invoice = _scoped_invoice(request.user, pk)  # authz + scope check
    form = PaymentForm(request.POST)
    if form.is_valid():
        try:
            services.record_payment(
                actor=request.user, invoice_id=invoice.pk, data=form.cleaned_data, request=request
            )
            messages.success(request, _("سُجّلت الدفعة."))
        except ValidationError as exc:
            messages.error(request, exc.messages[0] if exc.messages else _("تعذّر تسجيل الدفعة."))
    else:
        messages.error(request, _("بيانات الدفعة غير صالحة."))
    return redirect("finance:invoice_detail", pk=pk)


@require_POST
@require_capability(M)
def credit_note_create(request, pk):
    invoice = _scoped_invoice(request.user, pk)
    form = CreditNoteForm(request.POST)
    if form.is_valid():
        try:
            services.issue_credit_note(
                actor=request.user, invoice_id=invoice.pk, data=form.cleaned_data, request=request
            )
            messages.success(request, _("صدر الإشعار الدائن."))
        except ValidationError as exc:
            messages.error(request, exc.messages[0] if exc.messages else _("تعذّر إصدار الإشعار."))
    else:
        messages.error(request, _("بيانات الإشعار غير صالحة."))
    return redirect("finance:invoice_detail", pk=pk)


# ═══ Payments ═════════════════════════════════════════════
class PaymentListView(CapabilityRequiredMixin, LoginRequiredMixin, ListView):
    required_capability = V
    template_name = "finance/payment_list.html"
    context_object_name = "payments"

    def get_queryset(self):
        self.filter_form = PaymentFilterForm(self.request.GET or None)
        self.filter_form.is_valid()
        data = self.filter_form.cleaned_data if self.filter_form.is_bound else {}
        qs = payment_list(
            user=self.request.user,
            query=data.get("q", ""),
            method=data.get("method", ""),
            client_id=self.request.GET.get("client", ""),
            case_id=self.request.GET.get("case", ""),
        )
        assert_scoped(qs)
        return qs

    def get_context_data(self, **kwargs):
        page, count, querystring = _page(self.request, self.object_list)
        return {
            **super().get_context_data(object_list=page.object_list, **kwargs),
            "filter_form": self.filter_form,
            "page_obj": page,
            "payments": page.object_list,
            "total_count": count,
            "querystring": querystring,
            "can_manage": can(self.request.user, M),
        }


class PaymentDetailView(CapabilityRequiredMixin, LoginRequiredMixin, DetailView):
    required_capability = V
    template_name = "finance/payment_detail.html"
    context_object_name = "payment"

    def get_object(self, queryset=None):
        return _scoped_payment(self.request.user, self.kwargs["pk"])

    def get_context_data(self, **kwargs):
        return {
            **super().get_context_data(**kwargs),
            "can_manage": can(self.request.user, M),
            "reversals": list(self.object.reversals.all()),
            "reversal_form": PaymentReversalForm(),
        }


@require_POST
@require_capability(M)
def payment_reverse(request, pk):
    payment = _scoped_payment(request.user, pk)
    form = PaymentReversalForm(request.POST)
    if form.is_valid():
        try:
            services.reverse_payment(
                actor=request.user, payment_id=payment.pk, data=form.cleaned_data, request=request
            )
            messages.success(request, _("سُجّل استرجاع الدفعة."))
        except ValidationError as exc:
            messages.error(request, exc.messages[0] if exc.messages else _("تعذّر الاسترجاع."))
    else:
        messages.error(request, _("بيانات الاسترجاع غير صالحة."))
    return redirect("finance:payment_detail", pk=pk)


# ═══ Expenses ═════════════════════════════════════════════
class ExpenseListView(CapabilityRequiredMixin, LoginRequiredMixin, ListView):
    required_capability = V
    template_name = "finance/expense_list.html"
    context_object_name = "expenses"

    def get_queryset(self):
        self.filter_form = ExpenseFilterForm(self.request.GET or None)
        self.filter_form.is_valid()
        data = self.filter_form.cleaned_data if self.filter_form.is_bound else {}
        qs = expense_list(
            user=self.request.user,
            query=data.get("q", ""),
            category=data.get("category", ""),
            case_id=self.request.GET.get("case", ""),
            client_id=self.request.GET.get("client", ""),
        )
        assert_scoped(qs)
        return qs

    def get_context_data(self, **kwargs):
        page, count, querystring = _page(self.request, self.object_list)
        return {
            **super().get_context_data(object_list=page.object_list, **kwargs),
            "filter_form": self.filter_form,
            "page_obj": page,
            "expenses": page.object_list,
            "total_count": count,
            "querystring": querystring,
            "can_manage": can(self.request.user, M),
        }


class ExpenseDetailView(CapabilityRequiredMixin, LoginRequiredMixin, DetailView):
    required_capability = V
    template_name = "finance/expense_detail.html"
    context_object_name = "expense"

    def get_object(self, queryset=None):
        return _scoped_expense(self.request.user, self.kwargs["pk"])

    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), "can_manage": can(self.request.user, M)}


class _ExpenseFormMixin(CapabilityRequiredMixin, LoginRequiredMixin, FormView):
    required_capability = M
    form_class = ExpenseForm
    template_name = "finance/expense_form.html"

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "user": self.request.user}

    def get_success_url(self):
        return reverse("finance:expense_detail", args=[self.object.pk])


class ExpenseCreateView(_ExpenseFormMixin):
    def get_initial(self):
        initial = {}
        user = self.request.user
        for key, model in (("case", Case), ("client", Client)):
            val = self.request.GET.get(key)
            if str(val).isdigit() and model.objects.for_user(user).filter(pk=val).exists():
                initial[key] = val
        return initial

    def form_valid(self, form):
        self.object = services.create_expense(
            actor=self.request.user, data=form.cleaned_data, request=self.request
        )
        messages.success(self.request, _("سُجّل المصروف."))
        return redirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), "is_create": True}


class ExpenseUpdateView(_ExpenseFormMixin):
    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            self.expense_obj = _scoped_expense(request.user, kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "instance": self.expense_obj}

    def form_valid(self, form):
        try:
            self.object = services.update_expense(
                actor=self.request.user,
                expense=self.expense_obj,
                data=form.cleaned_data,
                request=self.request,
            )
        except ValidationError as exc:
            form.add_error(None, exc.messages)
            return self.form_invalid(form)
        messages.success(self.request, _("تم حفظ التعديلات."))
        return redirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        return {
            **super().get_context_data(**kwargs),
            "is_create": False,
            "expense": self.expense_obj,
        }


@require_POST
@require_capability(M)
def expense_retire(request, pk):
    expense = _scoped_expense(request.user, pk)
    services.retire_expense(actor=request.user, expense=expense, request=request)
    messages.success(request, _("سُحب المصروف."))
    return redirect("finance:expense_list")
