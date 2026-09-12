"""
Private storage for legal documents (spec §35, docs/adr/0030, docs/adr/0037).

The ``documents`` storage is a separate ``STORAGES`` entry so it is never the
default and never web-served. Both backends below refuse to build a URL — a
document is only ever reached through the audited download view. Tests bind
the entry to ``InMemoryStorage``.

Two backends, selected in ``config/settings/base.py`` by whether
``AWS_STORAGE_BUCKET_NAME`` is set:

- :class:`PrivateFileSystemStorage` — local disk. Default; what Docker/local
  deployments use, unchanged from before docs/adr/0037.
- :class:`PrivateS3Storage` — an S3-compatible bucket (AWS S3, Cloudflare R2,
  Backblaze B2, ...). Required on platforms with no persistent filesystem
  (e.g. Vercel serverless functions) — see docs/adr/0037.
"""

from __future__ import annotations

import uuid

from django.core.files.storage import FileSystemStorage, storages
from django.utils import timezone
from storages.backends.s3 import S3Storage


class PrivateFileSystemStorage(FileSystemStorage):
    """A filesystem storage with **no public URL**. ``FileSystemStorage`` falls
    back to ``MEDIA_URL`` when ``base_url`` is ``None``; this override makes
    ``.url()`` raise instead, so a private document can never leak a link."""

    def url(self, name):
        raise ValueError("Documents are private — use the download view, not a URL.")


class PrivateS3Storage(S3Storage):
    """Same no-URL contract as :class:`PrivateFileSystemStorage`, backed by an
    S3-compatible bucket. The bucket itself should also deny public access —
    this override is defense in depth, not the only control."""

    default_acl = "private"
    querystring_auth = False

    def url(self, name, parameters=None, expire=None, http_method=None):
        raise ValueError("Documents are private — use the download view, not a URL.")


def document_storage():
    return storages["documents"]


def document_upload_path(instance, filename: str) -> str:
    """``<year>/<month>/<uuid4>.<canonical-ext>`` — unpredictable, no
    user-controlled path segment (no traversal). The extension is the validator's
    canonical one, set on ``instance._canonical_ext`` by the service, never the
    client's ``filename``."""
    ext = getattr(instance, "_canonical_ext", "") or ""
    now = timezone.now()
    return f"{now:%Y/%m}/{uuid.uuid4().hex}{ext}"
