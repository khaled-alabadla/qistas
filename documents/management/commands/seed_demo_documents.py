"""Seed a couple of demo documents (spec §61). Idempotent-ish: skips cases that
already have a document. Generates tiny valid PDFs in-process."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand

from cases.models import Case
from documents.models import Document, DocumentCategory

User = get_user_model()

_MINIMAL_PDF = (
    b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 300 144]>>endobj\n"
    b"trailer<</Root 1 0 R>>\n%%EOF\n"
)


class Command(BaseCommand):
    help = "Create demo documents for cases that have none (idempotent)."

    def handle(self, *args, **options):
        actor = User.objects.filter(is_active=True).first()
        specs = [
            ("لائحة الدعوى.pdf", "لائحة الدعوى", DocumentCategory.PLEADING),
            ("وكالة المحامي.pdf", "وكالة عامة", DocumentCategory.POWER_OF_ATTORNEY),
            ("مذكرة جوابية.pdf", "مذكرة جوابية", DocumentCategory.PLEADING),
        ]
        created = 0
        for i, case in enumerate(Case.objects.select_related("client")[:6]):
            if case.documents.exists():
                continue
            filename, name, category = specs[i % len(specs)]
            doc = Document(
                name=name,
                document_type=category,
                case=case,
                client=case.client,
                content_type="application/pdf",
                size=len(_MINIMAL_PDF),
                original_filename=filename,
                uploaded_by=actor,
                updated_by=actor,
            )
            doc._canonical_ext = ".pdf"
            doc.file.save(filename, ContentFile(_MINIMAL_PDF), save=False)
            doc.save()
            created += 1
        self.stdout.write(self.style.SUCCESS(f"created {created} document(s)"))
