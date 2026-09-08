"""Trigram GIN indexes for case free-text search (docs/adr/0023, grill C5).

PostgreSQL only — guarded so a SQLite smoke run still migrates. Requires the
``pg_trgm`` extension (created in core migration 0002).
"""

from django.db import migrations

# Must cover every column in cases.models.SEARCH_FIELDS — an un-indexed column
# in the search OR forces a sequential scan and defeats the other indexes.
TRGM_COLUMNS = (
    "case_number",
    "title",
    "court_case_number",
    "internal_reference",
    "department",
)


def create_indexes(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for col in TRGM_COLUMNS:
        schema_editor.execute(
            f'CREATE INDEX IF NOT EXISTS cases_case_{col}_trgm '
            f'ON cases_case USING gin ("{col}" gin_trgm_ops)'
        )


def drop_indexes(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for col in TRGM_COLUMNS:
        schema_editor.execute(f"DROP INDEX IF EXISTS cases_case_{col}_trgm")


class Migration(migrations.Migration):
    dependencies = [
        ("cases", "0002_seed_case_types"),
        ("core", "0002_postgres_extensions"),
    ]

    operations = [migrations.RunPython(create_indexes, drop_indexes)]
