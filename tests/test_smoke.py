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
    """`check --deploy --fail-level WARNING` must be clean on prod-like settings —
    the exact gate CI runs. Catches e.g. security.W009 (weak SECRET_KEY)."""
    import secrets
    from io import StringIO

    from django.core.management import call_command

    settings.DEBUG = False
    settings.SECRET_KEY = secrets.token_urlsafe(64)  # strong, ephemeral
    settings.SECURE_HSTS_SECONDS = 31536000
    settings.SECURE_SSL_REDIRECT = True
    settings.SESSION_COOKIE_SECURE = True
    settings.CSRF_COOKIE_SECURE = True
    settings.SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    settings.SECURE_HSTS_PRELOAD = True
    out = StringIO()
    call_command("check", "--deploy", "--fail-level", "WARNING", stdout=out, stderr=out)


def test_short_secret_key_fails_deploy_check(settings):
    """Regression: a weak SECRET_KEY must still trip security.W009."""
    from io import StringIO

    from django.core.management import CommandError, call_command

    settings.DEBUG = False
    settings.SECRET_KEY = "too-short"
    with pytest.raises((CommandError, SystemExit)):
        call_command(
            "check",
            "--deploy",
            "--fail-level",
            "WARNING",
            stdout=StringIO(),
            stderr=StringIO(),
        )
