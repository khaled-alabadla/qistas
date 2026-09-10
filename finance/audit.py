"""Register the editable finance models with django-auditlog (docs/adr/0020).

Only the models that can actually change are registered — ``Payment`` /
``PaymentReversal`` / ``CreditNote`` are append-only, so an auditlog diff would
never have a second version. ``InvoiceLineItem`` changes are captured through the
parent invoice's ``INVOICE_UPDATED`` events.
"""

from __future__ import annotations

from auditlog.registry import auditlog

from finance.models import Expense, FeeAgreement, Invoice

auditlog.register(FeeAgreement, exclude_fields=["created_at", "updated_at"])
auditlog.register(Invoice, exclude_fields=["created_at", "updated_at"])
auditlog.register(Expense, exclude_fields=["created_at", "updated_at"])
