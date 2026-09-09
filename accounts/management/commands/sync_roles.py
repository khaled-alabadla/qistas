"""
Single source of truth for group -> Django-permission assignment (docs/adr/0007).

* Idempotent. Run on every deploy and in CI.
* ``--check`` exits non-zero if the live state has drifted from the desired
  mapping (used by a test + CI).

The capability layer (`core.permissions.capabilities`) is separate: it maps
groups -> named capabilities in code. This command keeps Django's own
model-permission grants aligned for the admin site and `has_perm` checks.
"""

from __future__ import annotations

from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand, CommandError

from core.permissions.capabilities import GROUPS
from core.permissions.capabilities import Group as GroupChoice

# group name -> exact set of "app_label.codename" it should hold.
# The capability layer drives in-app access; these keep Django model permissions
# aligned for the admin site and `has_perm` checks.
_CLIENT_VIEW = {"clients.view_client"}
_CLIENT_MANAGE = {
    "clients.view_client",
    "clients.add_client",
    "clients.change_client",
    "clients.view_sensitive_client",
}

_CASE_VIEW = {"cases.view_case", "cases.view_casetype", "courts.view_court"}
_CASE_MANAGE = {
    *_CASE_VIEW,
    "cases.add_case",
    "cases.change_case",
    "cases.add_caseparty",
    "cases.change_caseparty",
    "cases.delete_caseparty",
    "cases.add_casenote",
    "cases.add_caselawyer",
    "cases.delete_caselawyer",
}
_CASE_CONFIDENTIAL = {"cases.view_confidential_case"}

# Phase 4 — courts (full) + hearings.
_COURT_VIEW = {"courts.view_court"}
_COURT_MANAGE = {*_COURT_VIEW, "courts.add_court", "courts.change_court"}
_HEARING_VIEW = {"hearings.view_hearing"}
_HEARING_MANAGE = {*_HEARING_VIEW, "hearings.add_hearing", "hearings.change_hearing"}

# Phase 5 — tasks + deadlines (one capability pair, two models).
_TASK_VIEW = {"tasks.view_task", "tasks.view_deadline"}
_TASK_MANAGE = {
    *_TASK_VIEW,
    "tasks.add_task",
    "tasks.change_task",
    "tasks.delete_task",
    "tasks.add_deadline",
    "tasks.change_deadline",
}

# Phase 6 — documents (no delete codename — retired, never hard-deleted).
_DOCUMENT_VIEW = {"documents.view_document"}
_DOCUMENT_MANAGE = {*_DOCUMENT_VIEW, "documents.add_document", "documents.change_document"}

ROLE_PERMISSIONS: dict[str, set[str]] = {
    GroupChoice.OFFICE_MANAGER: {
        "accounts.view_user",
        "accounts.add_user",
        "accounts.change_user",
        "accounts.issue_temp_password",
        "auth.view_group",
        "auth.change_group",
        "audit.view_auditlog",
        *_CLIENT_MANAGE,
        *_CASE_MANAGE,
        *_CASE_CONFIDENTIAL,
        "cases.add_casetype",
        "cases.change_casetype",
        *_COURT_MANAGE,
        *_HEARING_MANAGE,
        *_TASK_MANAGE,
        *_DOCUMENT_MANAGE,
    },
    GroupChoice.LAWYER: (
        _CLIENT_MANAGE
        | _CASE_MANAGE
        | _CASE_CONFIDENTIAL
        | _COURT_VIEW
        | _HEARING_MANAGE
        | _TASK_MANAGE
        | _DOCUMENT_MANAGE
    ),
    GroupChoice.PARALEGAL: (
        _CLIENT_VIEW
        | _CASE_MANAGE
        | _COURT_VIEW
        | _HEARING_MANAGE
        | _TASK_MANAGE
        | _DOCUMENT_MANAGE
    ),
    GroupChoice.ADMIN_CLERK: (
        _CLIENT_MANAGE
        | _CASE_MANAGE
        | _COURT_VIEW
        | _HEARING_MANAGE
        | _TASK_MANAGE
        | _DOCUMENT_MANAGE
    ),
    GroupChoice.FINANCE_CLERK: (
        _CLIENT_VIEW | _CASE_VIEW | _HEARING_VIEW | _TASK_VIEW | _DOCUMENT_VIEW
    ),
}


def _permission(label: str) -> Permission | None:
    app_label, codename = label.split(".", 1)
    return Permission.objects.filter(content_type__app_label=app_label, codename=codename).first()


class Command(BaseCommand):
    help = "Ensure the role groups exist and hold exactly their mapped permissions."

    def add_arguments(self, parser):
        parser.add_argument(
            "--check",
            action="store_true",
            help="Report drift and exit non-zero without changing anything.",
        )

    def handle(self, *args, **options):
        check = options["check"]
        drift: list[str] = []
        missing_perms: list[str] = []

        for name in GROUPS:
            group, created = Group.objects.get_or_create(name=name)
            if created:
                drift.append(f"created group '{name}'")

            desired_labels = ROLE_PERMISSIONS.get(name, set())
            desired_perms = set()
            for label in desired_labels:
                perm = _permission(label)
                if perm is None:
                    missing_perms.append(f"{name}: permission '{label}' not found")
                    continue
                desired_perms.add(perm)

            current = set(group.permissions.all())
            to_add = desired_perms - current
            to_remove = current - desired_perms

            for perm in sorted(to_add, key=str):
                drift.append(f"+ {name}: {perm.content_type.app_label}.{perm.codename}")
            for perm in sorted(to_remove, key=str):
                drift.append(f"- {name}: {perm.content_type.app_label}.{perm.codename}")

            if not check and (to_add or to_remove):
                group.permissions.set(desired_perms)

        if missing_perms:
            for line in missing_perms:
                self.stderr.write(self.style.WARNING(line))
            if check:
                raise CommandError("sync_roles --check: unresolved permissions (run migrate).")

        if check and drift:
            for line in drift:
                self.stdout.write(line)
            raise CommandError("sync_roles --check: role permissions have drifted.")

        if drift:
            for line in drift:
                self.stdout.write(self.style.SUCCESS(line))
            self.stdout.write(self.style.SUCCESS("roles synced."))
        else:
            self.stdout.write("roles already in sync.")
