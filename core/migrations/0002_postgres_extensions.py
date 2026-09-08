"""Enable pg_trgm + unaccent (docs/adr/0023).

Guarded so a SQLite smoke run (`DJANGO_TEST_ENGINE=sqlite`) still migrates.
On managed PostgreSQL where CREATE EXTENSION needs elevated rights, create the
extensions out-of-band; `IF NOT EXISTS` then makes this a no-op.
"""

from django.db import migrations


def create_extensions(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    schema_editor.execute("CREATE EXTENSION IF NOT EXISTS unaccent")


def drop_extensions(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("DROP EXTENSION IF EXISTS unaccent")
    schema_editor.execute("DROP EXTENSION IF EXISTS pg_trgm")


class Migration(migrations.Migration):
    dependencies = [("core", "0001_initial")]

    operations = [migrations.RunPython(create_extensions, drop_extensions)]
