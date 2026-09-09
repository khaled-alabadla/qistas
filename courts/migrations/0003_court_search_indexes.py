"""Trigram GIN indexes for court free-text search (docs/adr/0023, grill C5).

PostgreSQL only — guarded so a SQLite smoke run still migrates. Requires the
``pg_trgm`` extension (created in core migration 0002).
"""

from django.db import migrations

# Must cover every column in courts.models.SEARCH_FIELDS — an un-indexed column
# in the search OR forces a sequential scan and defeats the other indexes.
TRGM_COLUMNS = (
    "name",
    "city",
    "department",
    "address",
)


def create_indexes(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for col in TRGM_COLUMNS:
        schema_editor.execute(
            f'CREATE INDEX IF NOT EXISTS courts_court_{col}_trgm '
            f'ON courts_court USING gin ("{col}" gin_trgm_ops)'
        )


def drop_indexes(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for col in TRGM_COLUMNS:
        schema_editor.execute(f"DROP INDEX IF EXISTS courts_court_{col}_trgm")


class Migration(migrations.Migration):
    dependencies = [
        ("courts", "0002_court_full_fields"),
        ("core", "0002_postgres_extensions"),
    ]

    operations = [migrations.RunPython(create_indexes, drop_indexes)]
