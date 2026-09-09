"""Permission-scoped read queries for documents (docs/adr/0019, 0030)."""

from __future__ import annotations

from documents.models import Document, DocumentCategory

_SELECT = ("case", "client", "uploaded_by")


def document_list(
    *,
    user,
    query: str = "",
    document_type: str = "",
    case_id: str = "",
    client_id: str = "",
    include_retired: bool = False,
):
    qs = Document.objects.for_user(user).select_related(*_SELECT)
    if not include_retired:
        qs = qs.alive()
    if query:
        qs = qs.search(query)
    if document_type in DocumentCategory.values:
        qs = qs.filter(document_type=document_type)
    if str(case_id).isdigit():
        qs = qs.filter(case_id=case_id)
    if str(client_id).isdigit():
        qs = qs.filter(client_id=client_id)
    return qs


def case_documents(case):
    return case.documents.filter(deleted_at__isnull=True).select_related("uploaded_by")


def client_documents(client):
    return client.documents.filter(deleted_at__isnull=True).select_related("uploaded_by", "case")
