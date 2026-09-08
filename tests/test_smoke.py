"""Cross-cutting smoke checks (docs/PHASE_1_PLAN.md §5)."""

import pytest
from django.core.management import call_command
from django.db import connection

pytestmark = pytest.mark.django_db


def test_no_missing_migrations():
    # Raises SystemExit(1) if makemigrations would create something.
    call_command("makemigrations", "--check", "--dry-run", verbosity=0)


def test_healthz_ok(client):
    resp = client.get("/healthz/")
    assert resp.status_code == 200
    assert resp.content == b"ok"


@pytest.mark.postgres
def test_postgres_extensions_present():
    if connection.vendor != "postgresql":
        pytest.skip("postgres only")
    with connection.cursor() as cur:
        cur.execute("SELECT extname FROM pg_extension")
        names = {r[0] for r in cur.fetchall()}
    assert {"pg_trgm", "unaccent"} <= names


def test_deploy_check_is_clean(settings):
    """`check --deploy` must not raise on prod-like settings."""
    from io import StringIO

    from django.core.management import call_command

    settings.DEBUG = False
    settings.SECURE_HSTS_SECONDS = 31536000
    settings.SECURE_SSL_REDIRECT = True
    settings.SESSION_COOKIE_SECURE = True
    settings.CSRF_COOKIE_SECURE = True
    settings.SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    settings.SECURE_HSTS_PRELOAD = True
    out = StringIO()
    call_command("check", "--deploy", "--fail-level", "ERROR", stdout=out, stderr=out)
