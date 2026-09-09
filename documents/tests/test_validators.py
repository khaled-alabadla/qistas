import pytest
from django import forms
from django.core.files.uploadedfile import SimpleUploadedFile

from documents.tests.factories import DOCX_BYTES, EXE_BYTES, MINIMAL_PDF, PNG_BYTES
from documents.validators import validate_upload

pytestmark = pytest.mark.django_db  # no DB needed, but keeps settings consistent


def _f(name, data, ct="application/octet-stream"):
    return SimpleUploadedFile(name, data, content_type=ct)


def test_accepts_pdf_and_returns_metadata():
    v = validate_upload(_f("brief.pdf", MINIMAL_PDF))
    assert v.canonical_ext == ".pdf"
    assert v.content_type == "application/pdf"
    assert v.size == len(MINIMAL_PDF)
    assert len(v.sha256) == 64


def test_accepts_png_and_docx():
    assert validate_upload(_f("scan.png", PNG_BYTES)).canonical_ext == ".png"
    assert validate_upload(_f("agreement.docx", DOCX_BYTES)).canonical_ext == ".docx"


def test_rejects_disallowed_magic():
    with pytest.raises(forms.ValidationError):
        validate_upload(_f("evil.exe", EXE_BYTES))


def test_rejects_extension_content_mismatch():
    # PDF bytes but a .png name -> the extension does not match the real content
    with pytest.raises(forms.ValidationError):
        validate_upload(_f("fake.png", MINIMAL_PDF))


def test_rejects_disguised_executable_as_pdf():
    # client lies with a .pdf name; the header is an EXE
    with pytest.raises(forms.ValidationError):
        validate_upload(_f("malware.pdf", EXE_BYTES))


def test_rejects_oversize(settings):
    settings.DOCUMENTS_MAX_UPLOAD_MB = 1
    big = _f("big.pdf", MINIMAL_PDF + b"\x00" * (1024 * 1024 + 10))
    with pytest.raises(forms.ValidationError):
        validate_upload(big)


def test_rejects_empty_file():
    with pytest.raises(forms.ValidationError):
        validate_upload(_f("empty.pdf", b""))


def test_accepts_plain_text_only_for_text_extension():
    from documents.validators import validate_upload as v

    assert v(_f("notes.txt", "ملاحظات عربية".encode())).canonical_ext == ".txt"
    with pytest.raises(forms.ValidationError):
        v(_f("notes.pdf", b"just plain text, no signature"))


def test_content_type_header_is_ignored():
    # client claims image/png but content + name are pdf -> still validated as pdf
    v = validate_upload(_f("real.pdf", MINIMAL_PDF, ct="image/png"))
    assert v.content_type == "application/pdf"
