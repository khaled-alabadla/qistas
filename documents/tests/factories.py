from __future__ import annotations

import factory

from documents.models import Document, DocumentCategory

MINIMAL_PDF = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n"
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
DOCX_BYTES = b"PK\x03\x04" + b"\x00" * 40
OLE_BYTES = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 40
EXE_BYTES = b"MZ\x90\x00" + b"\x00" * 40  # not allowed


class DocumentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Document

    name = factory.Sequence(lambda n: f"مستند اختبار {n}")
    document_type = DocumentCategory.OTHER
    content_type = "application/pdf"
    original_filename = "test.pdf"
    size = len(MINIMAL_PDF)
    sha256 = "0" * 64
    file = factory.django.FileField(filename="stored.pdf", data=MINIMAL_PDF)
