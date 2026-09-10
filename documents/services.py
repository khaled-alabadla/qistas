"""
Transactional writes for documents (spec §34–36, §46, docs/adr/0018, 0030).

Every security-sensitive action is audited with **metadata only** (name, type,
size, sha256, changed field names — never file contents, ADR-0009). A
case-linked upload / retire also records a ``CaseEvent`` (spec §26). A document
is retired (soft-deleted), never hard-deleted (ADR-0022). The file is immutable
once uploaded — only metadata is editable.
"""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from audit.events import log_event
from audit.models import AuditAction
from cases.models import CaseEventType
from cases.services import record_case_event
from documents.models import Document
from documents.validators import ValidatedUpload, validate_upload

METADATA_EDITABLE = ("name", "document_type", "description", "case", "client", "contract")


def _audit_meta(doc: Document) -> dict:
    return {
        "name": doc.name,
        "document_type": doc.document_type,
        "content_type": doc.content_type,
        "size": doc.size,
        "sha256": doc.sha256,
    }


@transaction.atomic
def create_document(
    *,
    actor,
    uploaded_file,
    data: dict,
    validated: ValidatedUpload | None = None,
    request=None,
) -> Document:
    """Validate + store an uploaded file with its metadata."""
    validated = validated or validate_upload(uploaded_file)

    doc = Document(
        name=data["name"],
        document_type=data.get("document_type") or "other",
        description=data.get("description", ""),
        case=data.get("case"),
        client=data.get("client"),
        contract=data.get("contract"),
        content_type=validated.content_type,
        size=validated.size,
        sha256=validated.sha256,
        original_filename=_safe_original_name(uploaded_file),
        uploaded_by=actor,
        updated_by=actor,
    )
    # Consumed by documents.storage.document_upload_path (canonical ext only).
    doc._canonical_ext = validated.canonical_ext
    uploaded_file.seek(0)
    doc.file = uploaded_file
    doc.full_clean(exclude=["file"])
    doc.save()

    if doc.case_id:
        record_case_event(
            doc.case,
            CaseEventType.DOCUMENT_ADDED,
            f"مستند جديد: {doc.name}",
            actor=actor,
            document_id=doc.pk,
        )
    log_event(
        request, AuditAction.DOCUMENT_UPLOADED, actor=actor, obj=doc, changes=_audit_meta(doc)
    )
    return doc


@transaction.atomic
def update_document(*, actor, document: Document, data: dict, request=None) -> Document:
    """Edit metadata only — the file is immutable in Phase 6."""
    data = {k: v for k, v in data.items() if k in METADATA_EDITABLE}
    stored = Document.objects.select_related("case", "client", "contract").get(pk=document.pk)
    changed = [f for f, v in data.items() if getattr(stored, f) != v]
    if not changed:
        return document
    for field, value in data.items():
        setattr(document, field, value)
    document.updated_by = actor
    document.full_clean(exclude=["file"])
    document.save(update_fields=[*data.keys(), "updated_by", "updated_at"])
    log_event(
        request,
        AuditAction.DOCUMENT_UPDATED,
        actor=actor,
        obj=document,
        changes={"fields": sorted(changed)},
    )
    return document


def record_download(*, actor, document: Document, request=None) -> None:
    """Audit-only (spec §46 'Document downloaded') — no CaseEvent (too noisy)."""
    log_event(
        request,
        AuditAction.DOCUMENT_DOWNLOADED,
        actor=actor,
        obj=document,
        changes={"name": document.name, "sha256": document.sha256, "size": document.size},
    )


@transaction.atomic
def retire_document(*, actor, document: Document, request=None) -> Document:
    if document.deleted_at is not None:
        return document
    document.deleted_at = timezone.now()
    document.deleted_by = actor
    document.save(update_fields=["deleted_at", "deleted_by"])
    if document.case_id:
        record_case_event(
            document.case,
            CaseEventType.DOCUMENT_REMOVED,
            f"سُحب المستند: {document.name}",
            actor=actor,
            document_id=document.pk,
        )
    log_event(
        request,
        AuditAction.DOCUMENT_RETIRED,
        actor=actor,
        obj=document,
        changes=_audit_meta(document),
    )
    return document


def _safe_original_name(uploaded_file) -> str:
    raw = (getattr(uploaded_file, "name", "") or "").strip()
    raw = raw.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    raw = raw.replace("\r", "").replace("\n", "").replace('"', "")
    return raw[:255]
