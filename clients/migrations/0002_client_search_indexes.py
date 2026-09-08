"""Trigram GIN indexes for client free-text search (docs/adr/0023, grill C5).

PostgreSQL only — guarded so a SQLite smoke run still migrates. Requires the
``pg_trgm`` extension (created in core migration 0002).
"""

from django.db import migrations

# Must cover every column in clients.models.SEARCH_FIELDS — an un-indexed column
# in the search OR forces a sequential scan and defeats the other indexes.
TRGM_COLUMNS = (
    "client_number",
    "full_name",
    "company_name",
    "phone",
    "secondary_phone",
    "email",
    "city",
)


def create_indexes(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for col in TRGM_COLUMNS:
        schema_editor.execute(
            f'CREATE INDEX IF NOT EXISTS clients_client_{col}_trgm '
            f'ON clients_client USING gin ("{col}" gin_trgm_ops)'
        )


def drop_indexes(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for col in TRGM_COLUMNS:
        schema_editor.execute(f"DROP INDEX IF EXISTS clients_client_{col}_trgm")


class Migration(migrations.Migration):
    dependencies = [
        ("clients", "0001_initial"),
        ("core", "0002_postgres_extensions"),
    ]

    operations = [migrations.RunPython(create_indexes, drop_indexes)]
