"""
Base settings for Qistas.

Environment-driven (see .env.example). Split into dev / prod / test.
Decisions: docs/adr/  ·  Overview: docs/architecture.md
"""

from __future__ import annotations

from pathlib import Path

import environ
from django.utils.translation import gettext_lazy as _

# ── Paths ────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
_env_file = BASE_DIR / ".env"
if _env_file.exists():
    env.read_env(str(_env_file))

# ── Core security ────────────────────────────────────────────
SECRET_KEY = env("DJANGO_SECRET_KEY", default="insecure-dev-key-override-in-env")
DEBUG = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

# ── Applications ─────────────────────────────────────────────
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
]

THIRD_PARTY_APPS = [
    "django_htmx",
    "auditlog",
    "axes",
    "django_otp",
    "django_otp.plugins.otp_totp",
    "django_otp.plugins.otp_static",
]

LOCAL_APPS = [
    "core",
    "accounts",
    "audit",
    "clients",
    "courts",
    "cases",
    "hearings",
    "agenda",
    "tasks",
    "documents",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# ── Middleware (order matters) ───────────────────────────────
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django_otp.middleware.OTPMiddleware",
    "auditlog.middleware.AuditlogMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Qistas auth/session middleware (after auth + otp are resolved):
    "accounts.middleware.LoginRequiredMiddleware",
    "accounts.middleware.MustChangePasswordMiddleware",
    "accounts.middleware.IdleTimeoutMiddleware",
    "accounts.middleware.MFAEnforcementMiddleware",
    # AxesMiddleware must come last so it sees the final response.
    "axes.middleware.AxesMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# ── Templates ───────────────────────────────────────────────
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.template.context_processors.debug",
                "django.template.context_processors.i18n",
                "django.template.context_processors.static",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.navigation",
                "core.context_processors.app_meta",
            ],
        },
    },
]

# ── Database ────────────────────────────────────────────────
DATABASES = {
    "default": env.db(
        "DATABASE_URL",
        default="postgres://qistas:qistas@localhost:5432/qistas",
    ),
}
DATABASES["default"].setdefault("ATOMIC_REQUESTS", False)
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DJANGO_CONN_MAX_AGE", default=60)

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ── Authentication ──────────────────────────────────────────
AUTH_USER_MODEL = "accounts.User"

AUTHENTICATION_BACKENDS = [
    # AxesBackend must be first: it raises PermissionDenied for locked accounts
    # before the real backend runs (see django-axes docs).
    "axes.backends.AxesBackend",
    "django.contrib.auth.backends.ModelBackend",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": env.int("DJANGO_PASSWORD_MIN_LENGTH", default=10)},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "core:landing"
LOGOUT_REDIRECT_URL = "accounts:login"

# Session / idle-timeout (docs/adr/0027, docs/architecture.md §5)
SESSION_COOKIE_AGE = env.int("DJANGO_SESSION_COOKIE_AGE", default=60 * 60 * 8)
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_SAVE_EVERY_REQUEST = True
IDLE_TIMEOUT_SECONDS = env.int("QISTAS_IDLE_TIMEOUT_SECONDS", default=60 * 30)

# ── django-axes: lock by username only, never by IP (docs/adr/0026, grill D2) ──
# The whole office shares one NAT IP; IP-based lockout would be a self-DoS.
SILENCED_SYSTEM_CHECKS = ["axes.W006"]
AXES_LOCKOUT_PARAMETERS = ["username"]
AXES_USERNAME_FORM_FIELD = "username"
AXES_USERNAME_CALLABLE = "accounts.axes.get_username"
AXES_FAILURE_LIMIT = env.int("AXES_FAILURE_LIMIT", default=5)
AXES_COOLOFF_TIME = env.float("AXES_COOLOFF_HOURS", default=0.5)  # hours
AXES_RESET_ON_SUCCESS = True
AXES_LOCKOUT_CALLABLE = "accounts.views.axes_lockout_response"
AXES_VERBOSE = True

# ── MFA (docs/adr/0017): enrollable, enforcement OFF by default ──
REQUIRE_MFA = env.bool("QISTAS_REQUIRE_MFA", default=False)
MFA_ENFORCED_GROUPS = env.list("QISTAS_MFA_ENFORCED_GROUPS", default=[])
MFA_RECOVERY_CODE_COUNT = 10
OTP_TOTP_ISSUER = "Qistas"

# ── auditlog ────────────────────────────────────────────────
AUDITLOG_INCLUDE_ALL_MODELS = False
AUDITLOG_DISABLE_ON_RAW_SAVE = True
# Trust X-Forwarded-For for AuditLog.ip_address only behind a trusted proxy that
# strips + re-sets it (docs/adr/0020). Off by default = use REMOTE_ADDR.
AUDIT_TRUST_XFF = env.bool("QISTAS_AUDIT_TRUST_XFF", default=False)

# ── Internationalization (docs/adr/0003, docs/adr/0016) ──────
LANGUAGE_CODE = "ar"
LANGUAGES = [("ar", _("Arabic")), ("en", _("English"))]
LOCALE_PATHS = [BASE_DIR / "locale"]
FORMAT_MODULE_PATH = ["config.formats"]
TIME_ZONE = env("QISTAS_TIME_ZONE", default="Asia/Hebron")
USE_I18N = True
USE_TZ = True

# ── Static / media ──────────────────────────────────────────
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
    # Private legal-document store (docs/adr/0030). `base_url=None` -> `.url`
    # raises; a document is only reachable through the audited download view.
    # Never web-served: no MEDIA route, no whitenoise mapping.
    "documents": {
        "BACKEND": "documents.storage.PrivateFileSystemStorage",
        "OPTIONS": {"location": str(BASE_DIR / "media" / "documents")},
    },
}
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# ── Documents (Phase 6, spec §35, docs/adr/0030) ─────────────
DOCUMENTS_MAX_UPLOAD_MB = env.int("QISTAS_DOCUMENTS_MAX_UPLOAD_MB", default=25)
# Stream uploads above 5 MB straight to a temp file (default is 2.5 MB).
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
FILE_UPLOAD_PERMISSIONS = 0o640

# ── Email ───────────────────────────────────────────────────
DEFAULT_FROM_EMAIL = env("DJANGO_DEFAULT_FROM_EMAIL", default="qistas@example.com")
SERVER_EMAIL = DEFAULT_FROM_EMAIL

# ── Security headers (tightened further in prod.py) ──────────
SESSION_COOKIE_HTTPONLY = True
# HTMX gets the token from a template-rendered hx-headers attr (see base.html),
# so the cookie itself can stay HttpOnly.
CSRF_COOKIE_HTTPONLY = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"

# ── Messages → Tailwind-friendly tags ───────────────────────
from django.contrib.messages import constants as _messages  # noqa: E402

MESSAGE_TAGS = {
    _messages.DEBUG: "debug",
    _messages.INFO: "info",
    _messages.SUCCESS: "success",
    _messages.WARNING: "warning",
    _messages.ERROR: "error",
}

# ── Logging (docs/adr/0009: never log sensitive fields) ──────
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "redact_sensitive": {"()": "core.sensitive.SensitiveDataFilter"},
    },
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {name} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
            "filters": ["redact_sensitive"],
        },
    },
    "root": {"handlers": ["console"], "level": env("DJANGO_LOG_LEVEL", default="INFO")},
    "loggers": {
        "django.security": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "qistas": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}
