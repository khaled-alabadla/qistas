"""Trigram GIN indexes for finance free-text search (docs/adr/0023).

PostgreSQL only — guarded so a SQLite smoke run still migrates. Requires the
``pg_trgm`` extension (created in core migration 0002).
"""

from django.db import migrations

# Must cover every column in the corresponding *_SEARCH_FIELDS in finance.models
# (payment search is `reference` only — the invoice-number match is a join, not a
# column on finance_payment). `notes` on the invoice is a body but it is the only
# free-text handle a draft invoice has before it gets a number, so it is indexed.
FEE_AGREEMENT_TRGM_COLUMNS = ("reference", "description")
INVOICE_TRGM_COLUMNS = ("invoice_number", "notes")
EXPENSE_TRGM_COLUMNS = ("reference", "description")
PAYMENT_TRGM_COLUMNS = ("reference",)

_TABLES = {
    "finance_feeagreement": FEE_AGREEMENT_TRGM_COLUMNS,
    "finance_invoice": INVOICE_TRGM_COLUMNS,
    "finance_expense": EXPENSE_TRGM_COLUMNS,
    "finance_payment": PAYMENT_TRGM_COLUMNS,
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
        ("finance", "0001_initial"),
        ("core", "0002_postgres_extensions"),
    ]

    operations = [migrations.RunPython(create_indexes, drop_indexes)]
