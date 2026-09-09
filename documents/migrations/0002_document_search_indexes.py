"""Trigram GIN indexes for document free-text search (docs/adr/0023).

PostgreSQL only — guarded so a SQLite smoke run still migrates. Requires the
``pg_trgm`` extension (created in core migration 0002).
"""

from django.db import migrations

# Must cover every column in documents.models.SEARCH_FIELDS.
TRGM_COLUMNS = ("name", "description", "original_filename")


def create_indexes(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for col in TRGM_COLUMNS:
        schema_editor.execute(
            f'CREATE INDEX IF NOT EXISTS documents_document_{col}_trgm '
            f'ON documents_document USING gin ("{col}" gin_trgm_ops)'
        )


def drop_indexes(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for col in TRGM_COLUMNS:
        schema_editor.execute(f"DROP INDEX IF EXISTS documents_document_{col}_trgm")


class Migration(migrations.Migration):
    dependencies = [
        ("documents", "0001_initial"),
        ("core", "0002_postgres_extensions"),
    ]

    operations = [migrations.RunPython(create_indexes, drop_indexes)]
