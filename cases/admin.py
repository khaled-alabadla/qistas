from __future__ import annotations

from django.contrib import admin

from cases.models import (
    Case,
    CaseConfidential,
    CaseEvent,
    CaseLawyer,
    CaseNote,
    CaseParty,
    CaseType,
)


@admin.register(CaseType)
class CaseTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active", "order")
    list_editable = ("is_active", "order")


class CasePartyInline(admin.TabularInline):
    model = CaseParty
    extra = 0
    fields = ("party_role", "name", "phone", "email", "linked_client")


class CaseLawyerInline(admin.TabularInline):
    model = CaseLawyer
    extra = 0
    fk_name = "case"
    fields = ("lawyer", "added_by", "added_at")
    readonly_fields = ("added_at",)


@admin.register(Case)
class CaseAdmin(admin.ModelAdmin):
    list_display = (
        "case_number",
        "title",
        "type",
        "client",
        "status",
        "priority",
        "assigned_lawyer",
        "court",
    )
    list_filter = ("status", "priority", "type", "court")
    search_fields = ("case_number", "title", "court_case_number", "internal_reference")
    autocomplete_fields = ("client",)
    readonly_fields = ("case_number", "created_at", "updated_at", "created_by", "updated_by")
    inlines = (CaseLawyerInline, CasePartyInline)

    def has_delete_permission(self, request, obj=None):
        # Cases are closed, never deleted (docs/adr/0022).
        return False


@admin.register(CaseNote)
class CaseNoteAdmin(admin.ModelAdmin):
    list_display = ("case", "kind", "author", "created_at", "deleted_at")
    list_filter = ("kind",)
    search_fields = ("case__case_number", "body")


@admin.register(CaseEvent)
class CaseEventAdmin(admin.ModelAdmin):
    list_display = ("case", "event_type", "summary", "actor", "occurred_at")
    list_filter = ("event_type",)
    search_fields = ("case__case_number", "summary")
    readonly_fields = ("case", "event_type", "summary", "detail", "actor", "occurred_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CaseConfidential)
class CaseConfidentialAdmin(admin.ModelAdmin):
    list_display = ("case", "updated_by", "updated_at")
    readonly_fields = ("case", "updated_by", "updated_at")

    def has_add_permission(self, request):
        return False
