"""Seed the five role groups (docs/adr/0007).

Only creates the Group rows. Permission assignment is owned by the idempotent
``sync_roles`` management command, run on deploy and in CI.
"""

from django.db import migrations

GROUP_NAMES = [
    "office_manager",
    "lawyer",
    "paralegal",
    "admin_clerk",
    "finance_clerk",
]


def create_groups(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    for name in GROUP_NAMES:
        Group.objects.get_or_create(name=name)


def remove_groups(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name__in=GROUP_NAMES).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0001_initial"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [migrations.RunPython(create_groups, remove_groups)]
