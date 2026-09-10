from __future__ import annotations

from django.contrib import admin

from finance.models import (
    CreditNote,
    Expense,
    FeeAgreement,
    Invoice,
    InvoiceLineItem,
    Payment,
    PaymentReversal,
)

_READONLY_AUTHOR = ("created_at", "updated_at", "created_by", "updated_by")


@admin.register(FeeAgreement)
class FeeAgreementAdmin(admin.ModelAdmin):
    list_display = ("reference", "case", "fee_type", "status", "currency", "created_at")
    list_filter = ("status", "fee_type", "currency")
    search_fields = ("reference", "description", "case__case_number")
    autocomplete_fields = ("case",)
    readonly_fields = ("reference", *_READONLY_AUTHOR)

    def has_delete_permission(self, request, obj=None):
        return False


class InvoiceLineItemInline(admin.TabularInline):
    model = InvoiceLineItem
    extra = 0
    readonly_fields = ("line_total",)

    def has_add_permission(self, request, obj=None):
        return obj is not None and obj.status == "draft"

    def has_change_permission(self, request, obj=None):
        return obj is None or obj.status == "draft"

    def has_delete_permission(self, request, obj=None):
        return obj is None or obj.status == "draft"


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = (
        "__str__",
        "client",
        "case",
        "status",
        "total",
        "amount_paid",
        "currency",
        "issue_date",
        "due_date",
    )
    list_filter = ("status", "currency")
    search_fields = ("invoice_number", "notes", "client__client_number", "case__case_number")
    autocomplete_fields = ("client", "case", "fee_agreement")
    inlines = [InvoiceLineItemInline]
    readonly_fields = (
        "invoice_number",
        "subtotal",
        "tax_amount",
        "total",
        "amount_paid",
        "issue_date",
        *_READONLY_AUTHOR,
    )

    def get_readonly_fields(self, request, obj=None):
        ro = list(super().get_readonly_fields(request, obj))
        if obj and obj.status != "draft":  # issued = immutable (ADR-0012)
            ro += [
                "client",
                "case",
                "fee_agreement",
                "discount",
                "tax_rate",
                "status",
                "notes",
                "due_date",
            ]
        return tuple(ro)

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("reference", "invoice", "amount", "method", "paid_on", "created_by")
    list_filter = ("method",)
    search_fields = ("reference", "invoice__invoice_number", "external_reference")
    readonly_fields = (
        "reference",
        "invoice",
        "amount",
        "paid_on",
        "method",
        "external_reference",
        "note",
        *_READONLY_AUTHOR,
    )

    def has_add_permission(self, request):
        return False  # payments are recorded through the service only

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PaymentReversal)
class PaymentReversalAdmin(admin.ModelAdmin):
    list_display = ("payment", "amount", "reversed_on", "created_by")
    readonly_fields = ("payment", "amount", "reason", "reversed_on", *_READONLY_AUTHOR)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CreditNote)
class CreditNoteAdmin(admin.ModelAdmin):
    list_display = ("credit_number", "invoice", "amount", "issued_on", "created_by")
    search_fields = ("credit_number", "invoice__invoice_number")
    readonly_fields = (
        "credit_number",
        "invoice",
        "amount",
        "reason",
        "issued_on",
        *_READONLY_AUTHOR,
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = (
        "reference",
        "description",
        "amount",
        "category",
        "spent_on",
        "case",
        "client",
        "deleted_at",
    )
    list_filter = ("category", "currency")
    search_fields = ("reference", "description", "case__case_number", "client__client_number")
    autocomplete_fields = ("case", "client")
    readonly_fields = ("reference", "deleted_at", "deleted_by", *_READONLY_AUTHOR)

    def has_delete_permission(self, request, obj=None):
        return False  # soft-delete only (ADR-0022)
