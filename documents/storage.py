"""
Private storage for legal documents (spec §35, docs/adr/0030).

The ``documents`` storage is a separate ``STORAGES`` entry so it is never the
default and never web-served. :class:`PrivateFileSystemStorage` also refuses to
build a URL — a document is only ever reached through the audited download view.
Tests bind the entry to ``InMemoryStorage``.
"""

from __future__ import annotations

import uuid

from django.core.files.storage import FileSystemStorage, storages
from django.utils import timezone


class PrivateFileSystemStorage(FileSystemStorage):
    """A filesystem storage with **no public URL**. ``FileSystemStorage`` falls
    back to ``MEDIA_URL`` when ``base_url`` is ``None``; this override makes
    ``.url()`` raise instead, so a private document can never leak a link."""

    def url(self, name):
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
