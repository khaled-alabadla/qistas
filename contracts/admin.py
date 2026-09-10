from __future__ import annotations

from django.contrib import admin

from contracts.models import Contract


@admin.register(Contract)
class ContractAdmin(admin.ModelAdmin):
    list_display = (
        "contract_number",
        "title",
        "contract_type",
        "status",
        "client",
        "case",
        "start_date",
        "end_date",
        "value",
        "currency",
    )
    list_filter = ("status", "contract_type", "currency")
    search_fields = (
        "contract_number",
        "title",
        "description",
        "client__client_number",
        "case__case_number",
    )
    autocomplete_fields = ("client", "case")
    readonly_fields = (
        "contract_number",
        "created_at",
        "updated_at",
        "created_by",
        "updated_by",
    )

    def has_delete_permission(self, request, obj=None):
        # A contract is legally significant — never hard-deleted (docs/adr/0022, 0031).
        # "cancel" is a status transition.
        return False
