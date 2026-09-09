"""Test settings. Targets PostgreSQL by default (docs/adr/0025).

For a fast local smoke run without a database server:
    DJANGO_TEST_ENGINE=sqlite pytest
PostgreSQL-only tests are marked `@pytest.mark.postgres` and skip elsewhere.
"""

from __future__ import annotations

from .base import *
from .base import BASE_DIR, INSTALLED_APPS, env

DEBUG = False

# Test-only app holding a throwaway model for the object-scoping framework tests.
INSTALLED_APPS = [*INSTALLED_APPS, "core.tests.testapp"]

if env("DJANGO_TEST_ENGINE", default="postgres") == "sqlite":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "test-db.sqlite3",
        }
    }

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# Deterministic + inert for tests.
REQUIRE_MFA = False
MFA_ENFORCED_GROUPS = []
AXES_ENABLED = True
AXES_FAILURE_LIMIT = 3
AXES_COOLOFF_TIME = 0.01

SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    "documents": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
}
