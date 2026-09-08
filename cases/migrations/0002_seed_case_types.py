"""Seed the configurable ``CaseType`` table with the office's default set
(spec §23). Reversible; safe to re-run (get_or_create)."""

from django.db import migrations

DEFAULTS = [
    "مدنية",
    "تجارية",
    "عمالية",
    "جزائية",
    "أحوال شخصية",
    "إدارية",
    "أخرى",
]


def seed(apps, schema_editor):
    CaseType = apps.get_model("cases", "CaseType")
    for order, name in enumerate(DEFAULTS):
        CaseType.objects.get_or_create(name=name, defaults={"order": order})


def unseed(apps, schema_editor):
    CaseType = apps.get_model("cases", "CaseType")
    CaseType.objects.filter(name__in=DEFAULTS, cases__isnull=True).delete()


class Migration(migrations.Migration):
    dependencies = [("cases", "0001_initial")]

    operations = [migrations.RunPython(seed, unseed)]
