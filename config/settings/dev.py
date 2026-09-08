"""Development settings — never use in production."""

from __future__ import annotations

from .base import *
from .base import INSTALLED_APPS, MIDDLEWARE, env

DEBUG = True
ALLOWED_HOSTS = ["*"]

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# django-debug-toolbar (dev only)
if env.bool("QISTAS_ENABLE_DEBUG_TOOLBAR", default=False):
    INSTALLED_APPS += ["debug_toolbar"]
    MIDDLEWARE.insert(
        MIDDLEWARE.index("django.middleware.common.CommonMiddleware") + 1,
        "debug_toolbar.middleware.DebugToolbarMiddleware",
    )
    INTERNAL_IPS = ["127.0.0.1"]

# Relax cookie security for plain-HTTP local dev.
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
