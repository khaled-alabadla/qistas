from __future__ import annotations

from django.urls import path

from finance import views

app_name = "finance"

urlpatterns = [
    # Fee agreements
    path("fee-agreements/", views.FeeAgreementListView.as_view(), name="fee_agreement_list"),
    path(
        "fee-agreements/new/", views.FeeAgreementCreateView.as_view(), name="fee_agreement_create"
    ),
    path(
        "fee-agreements/<int:pk>/",
        views.FeeAgreementDetailView.as_view(),
        name="fee_agreement_detail",
    ),
    path(
        "fee-agreements/<int:pk>/edit/",
        views.FeeAgreementUpdateView.as_view(),
        name="fee_agreement_update",
    ),
    path(
        "fee-agreements/<int:pk>/status/", views.fee_agreement_status, name="fee_agreement_status"
    ),
    # Invoices
    path("invoices/", views.InvoiceListView.as_view(), name="invoice_list"),
    path("invoices/new/", views.InvoiceCreateView.as_view(), name="invoice_create"),
    path("invoices/<int:pk>/", views.InvoiceDetailView.as_view(), name="invoice_detail"),
    path("invoices/<int:pk>/edit/", views.InvoiceUpdateView.as_view(), name="invoice_update"),
    path("invoices/<int:pk>/lines/add/", views.invoice_line_add, name="invoice_line_add"),
    path(
        "invoices/<int:pk>/lines/<int:line_pk>/remove/",
        views.invoice_line_remove,
        name="invoice_line_remove",
    ),
    path("invoices/<int:pk>/issue/", views.invoice_issue, name="invoice_issue"),
    path("invoices/<int:pk>/cancel/", views.invoice_cancel, name="invoice_cancel"),
    path("invoices/<int:pk>/pay/", views.payment_create, name="payment_create"),
    path("invoices/<int:pk>/credit-note/", views.credit_note_create, name="credit_note_create"),
    # Payments
    path("payments/", views.PaymentListView.as_view(), name="payment_list"),
    path("payments/<int:pk>/", views.PaymentDetailView.as_view(), name="payment_detail"),
    path("payments/<int:pk>/reverse/", views.payment_reverse, name="payment_reverse"),
    # Expenses
    path("expenses/", views.ExpenseListView.as_view(), name="expense_list"),
    path("expenses/new/", views.ExpenseCreateView.as_view(), name="expense_create"),
    path("expenses/<int:pk>/", views.ExpenseDetailView.as_view(), name="expense_detail"),
    path("expenses/<int:pk>/edit/", views.ExpenseUpdateView.as_view(), name="expense_update"),
    path("expenses/<int:pk>/retire/", views.expense_retire, name="expense_retire"),
]
