import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from audit.models import AuditAction, AuditLog
from cases.models import CaseEventType
from cases.tests.factories import CaseFactory
from documents import services
from documents.models import Document
from documents.tests.factories import MINIMAL_PDF, PNG_BYTES, DocumentFactory

pytestmark = pytest.mark.django_db


def _upload(name="brief.pdf", data=MINIMAL_PDF):
    return SimpleUploadedFile(name, data, content_type="application/pdf")


def test_create_document_stores_metadata_and_audits(office_manager):
    case = CaseFactory()
    doc = services.create_document(
        actor=office_manager,
        uploaded_file=_upload(),
        data={
            "name": "لائحة",
            "document_type": "pleading",
            "description": "",
            "case": case,
            "client": None,
        },
    )
    assert doc.uploaded_by == office_manager
    assert doc.size == len(MINIMAL_PDF)
    assert doc.content_type == "application/pdf"
    assert len(doc.sha256) == 64
    assert doc.original_filename == "brief.pdf"
    # stored path is unpredictable and carries no client filename
    assert "brief" not in doc.file.name
    assert case.events.filter(event_type=CaseEventType.DOCUMENT_ADDED).exists()
    log = AuditLog.objects.get(action=AuditAction.DOCUMENT_UPLOADED, entity_id=str(doc.pk))
    assert log.changes["sha256"] == doc.sha256
    assert set(log.changes) == {"name", "document_type", "content_type", "size", "sha256"}
    assert "%PDF" not in str(log.changes)  # no raw file bytes ever


def test_create_document_without_case_has_no_case_event(office_manager):
    doc = services.create_document(
        actor=office_manager,
        uploaded_file=_upload("scan.png", PNG_BYTES),
        data={
            "name": "صورة",
            "document_type": "other",
            "description": "",
            "case": None,
            "client": None,
        },
    )
    assert doc.content_type == "image/png"
    assert doc.case_id is None
    # exactly one upload event, no case timeline touched
    assert AuditLog.objects.filter(action=AuditAction.DOCUMENT_UPLOADED).count() == 1


def test_create_document_rejects_bad_file(office_manager):
    from django import forms

    with pytest.raises(forms.ValidationError):
        services.create_document(
            actor=office_manager,
            uploaded_file=SimpleUploadedFile("x.pdf", b"MZ\x90\x00 not a pdf"),
            data={
                "name": "x",
                "document_type": "other",
                "description": "",
                "case": None,
                "client": None,
            },
        )
    assert not Document.objects.exists()


def test_update_document_metadata_only(office_manager):
    doc = DocumentFactory(name="قديم")
    original_file = doc.file.name
    services.update_document(actor=office_manager, document=doc, data={"name": "جديد"})
    doc.refresh_from_db()
    assert doc.name == "جديد"
    assert doc.file.name == original_file  # file untouched
    assert AuditLog.objects.filter(action=AuditAction.DOCUMENT_UPDATED).exists()


def test_update_document_noop(office_manager):
    doc = DocumentFactory(name="ثابت")
    services.update_document(actor=office_manager, document=doc, data={"name": "ثابت"})
    assert not AuditLog.objects.filter(action=AuditAction.DOCUMENT_UPDATED).exists()


def test_record_download_audits_only(office_manager):
    doc = DocumentFactory(case=CaseFactory())
    services.record_download(actor=office_manager, document=doc)
    assert AuditLog.objects.filter(
        action=AuditAction.DOCUMENT_DOWNLOADED, entity_id=str(doc.pk)
    ).exists()
    assert not doc.case.events.exists()  # downloads never touch the case timeline


def test_retire_is_soft_and_idempotent(office_manager):
    case = CaseFactory()
    doc = DocumentFactory(case=case)
    services.retire_document(actor=office_manager, document=doc)
    doc.refresh_from_db()
    assert doc.deleted_at is not None and doc.deleted_by == office_manager
    assert Document.objects.filter(pk=doc.pk).exists()  # row kept
    assert doc not in Document.objects.alive()
    assert case.events.filter(event_type=CaseEventType.DOCUMENT_REMOVED).exists()
    assert AuditLog.objects.filter(action=AuditAction.DOCUMENT_RETIRED).exists()
    services.retire_document(actor=office_manager, document=doc)
    assert AuditLog.objects.filter(action=AuditAction.DOCUMENT_RETIRED).count() == 1
