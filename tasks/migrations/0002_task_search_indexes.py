"""Trigram GIN indexes for task + deadline free-text search (docs/adr/0023).

PostgreSQL only — guarded so a SQLite smoke run still migrates. Requires the
``pg_trgm`` extension (created in core migration 0002).
"""

from django.db import migrations

# Must cover every column in tasks.models.TASK_SEARCH_FIELDS /
# DEADLINE_SEARCH_FIELDS — an un-indexed column in the icontains OR forces a
# sequential scan.
TASK_TRGM_COLUMNS = ("title", "description")
DEADLINE_TRGM_COLUMNS = ("title", "description")

_TABLES = {
    "tasks_task": TASK_TRGM_COLUMNS,
    "tasks_deadline": DEADLINE_TRGM_COLUMNS,
}


def create_indexes(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for table, cols in _TABLES.items():
        for col in cols:
            schema_editor.execute(
                f'CREATE INDEX IF NOT EXISTS {table}_{col}_trgm '
                f'ON {table} USING gin ("{col}" gin_trgm_ops)'
            )


def drop_indexes(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for table, cols in _TABLES.items():
        for col in cols:
            schema_editor.execute(f"DROP INDEX IF EXISTS {table}_{col}_trgm")


class Migration(migrations.Migration):
    dependencies = [
        ("tasks", "0001_initial"),
        ("core", "0002_postgres_extensions"),
    ]

    operations = [migrations.RunPython(create_indexes, drop_indexes)]
