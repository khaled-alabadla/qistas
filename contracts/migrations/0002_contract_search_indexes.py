"""Trigram GIN indexes for contract free-text search (docs/adr/0023).

PostgreSQL only — guarded so a SQLite smoke run still migrates. Requires the
``pg_trgm`` extension (created in core migration 0002).
"""

from django.db import migrations

# Must cover every column in contracts.models.SEARCH_FIELDS — `notes` and `value`
# are deliberately NOT indexed (spec §4).
TRGM_COLUMNS = ("contract_number", "title", "description")


def create_indexes(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for col in TRGM_COLUMNS:
        schema_editor.execute(
            f'CREATE INDEX IF NOT EXISTS contracts_contract_{col}_trgm '
            f'ON contracts_contract USING gin ("{col}" gin_trgm_ops)'
        )


def drop_indexes(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for col in TRGM_COLUMNS:
        schema_editor.execute(f"DROP INDEX IF EXISTS contracts_contract_{col}_trgm")


class Migration(migrations.Migration):
    dependencies = [
        ("contracts", "0001_initial"),
        ("core", "0002_postgres_extensions"),
    ]

    operations = [migrations.RunPython(create_indexes, drop_indexes)]
