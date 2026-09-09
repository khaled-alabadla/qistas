"""
Upload validation for documents (spec §35, docs/adr/0030).

* **Never trust the uploaded filename** — the stored name is a uuid4.
* **Never trust the client Content-Type** — it is not read here.
* Deny-by-default: a header that matches no curated signature is rejected.
* No `libmagic` — a small hand-rolled signature table keeps validation identical
  on the Windows editor host and Linux production.

``validate_upload(file)`` raises ``django.forms.ValidationError`` (Arabic) on any
failure and otherwise returns a :class:`ValidatedUpload`.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass

from django import forms
from django.conf import settings
from django.utils.translation import gettext_lazy as _

_DEFAULT_MAX_MB = 25
_HEADER_BYTES = 8192
_HASH_CHUNK = 65536


@dataclass(frozen=True)
class ValidatedUpload:
    canonical_ext: str  # e.g. ".pdf" — what the stored file is named with
    content_type: str  # detected, for the download response
    size: int
    sha256: str


# family key -> (canonical extension, accepted client extensions, content type)
_FAMILIES = {
    "pdf": (".pdf", {".pdf"}, "application/pdf"),
    "png": (".png", {".png"}, "image/png"),
    "jpeg": (".jpg", {".jpg", ".jpeg"}, "image/jpeg"),
    "gif": (".gif", {".gif"}, "image/gif"),
    "tiff": (".tiff", {".tif", ".tiff"}, "image/tiff"),
    "zip_office": (
        ".docx",
        {".docx", ".xlsx", ".pptx"},
        "application/vnd.openxmlformats-officedocument",
    ),
    "ole_office": (
        ".doc",
        {".doc", ".xls", ".ppt"},
        "application/msword",
    ),
    "rtf": (".rtf", {".rtf"}, "application/rtf"),
    "text": (".txt", {".txt", ".csv", ".md", ".text"}, "text/plain"),
}

# byte-prefix signatures -> family key
_SIGNATURES: list[tuple[bytes, str]] = [
    (b"%PDF-", "pdf"),
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"\xff\xd8\xff", "jpeg"),
    (b"GIF87a", "gif"),
    (b"GIF89a", "gif"),
    (b"II*\x00", "tiff"),
    (b"MM\x00*", "tiff"),
    (b"PK\x03\x04", "zip_office"),
    (b"PK\x05\x06", "zip_office"),
    (b"PK\x07\x08", "zip_office"),
    (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", "ole_office"),
    (b"{\\rtf", "rtf"),
]


def _max_bytes() -> int:
    return int(getattr(settings, "DOCUMENTS_MAX_UPLOAD_MB", _DEFAULT_MAX_MB)) * 1024 * 1024


def allowed_extensions() -> set[str]:
    exts: set[str] = set()
    for _canon, accepted, _ct in _FAMILIES.values():
        exts |= accepted
    return exts


def _looks_like_text(head: bytes) -> bool:
    if b"\x00" in head:
        return False
    for enc in ("utf-8", "latin-1"):
        try:
            head.decode(enc)
            return True
        except UnicodeDecodeError:
            continue
    return False


def _detect_family(head: bytes, client_ext: str) -> str | None:
    for prefix, family in _SIGNATURES:
        if head.startswith(prefix):
            return family
    # text has no signature — only accept it for a declared text extension
    if client_ext in _FAMILIES["text"][1] and _looks_like_text(head):
        return "text"
    return None


def validate_upload(uploaded_file) -> ValidatedUpload:
    """Validate size + magic bytes + extension agreement; stream the sha256."""
    name = getattr(uploaded_file, "name", "") or ""
    client_ext = os.path.splitext(name)[1].lower()

    size = getattr(uploaded_file, "size", None)
    if size is None:  # pragma: no cover - defensive
        uploaded_file.seek(0, os.SEEK_END)
        size = uploaded_file.tell()
    if size <= 0:
        raise forms.ValidationError(_("الملف فارغ."))
    max_bytes = _max_bytes()
    if size > max_bytes:
        raise forms.ValidationError(
            _("حجم الملف يتجاوز الحد المسموح (%(mb)s ميغابايت).")
            % {"mb": max_bytes // (1024 * 1024)}
        )

    uploaded_file.seek(0)
    head = uploaded_file.read(_HEADER_BYTES)
    hasher = hashlib.sha256()
    hasher.update(head)
    while True:
        chunk = uploaded_file.read(_HASH_CHUNK)
        if not chunk:
            break
        hasher.update(chunk)
    uploaded_file.seek(0)

    family = _detect_family(head, client_ext)
    if family is None:
        raise forms.ValidationError(_("نوع الملف غير مدعوم أو محتواه لا يطابق امتداده."))

    canonical_ext, accepted_exts, content_type = _FAMILIES[family]
    if client_ext and client_ext not in accepted_exts:
        raise forms.ValidationError(
            _("امتداد الملف (%(ext)s) لا يطابق نوع محتواه الفعلي.") % {"ext": client_ext}
        )

    return ValidatedUpload(
        canonical_ext=canonical_ext,
        content_type=content_type,
        size=size,
        sha256=hasher.hexdigest(),
    )
