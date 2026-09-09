import datetime as dt

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from audit.models import AuditAction, AuditLog
from cases.models import CaseStatus
from cases.tests.factories import CaseFactory
from documents.models import Document
from documents.tests.factories import EXE_BYTES, MINIMAL_PDF, DocumentFactory

pytestmark = pytest.mark.django_db


def _upload(name="brief.pdf", data=MINIMAL_PDF):
    return SimpleUploadedFile(name, data, content_type="application/pdf")


# ── list / detail ──────────────────────────────────────────
def test_list_requires_login(client):
    resp = client.get(reverse("documents:list"))
    assert resp.status_code == 302
    assert reverse("accounts:login") in resp["Location"]


def test_list_renders_for_any_staff_hides_retired(client, finance_clerk):
    DocumentFactory()
    DocumentFactory(deleted_at=dt.datetime.now(tz=dt.UTC))
    client.force_login(finance_clerk)
    resp = client.get(reverse("documents:list"))
    assert resp.status_code == 200
    assert resp.context["total_count"] == 1


def test_list_paginates_and_keeps_scope_on_page_2(client, office_manager):
    DocumentFactory.create_batch(30)
    client.force_login(office_manager)
    p1 = client.get(reverse("documents:list"))
    assert len(p1.context["documents"]) == 25 and p1.context["total_count"] == 30
    p2 = client.get(reverse("documents:list"), {"page": "2"})
    assert len(p2.context["documents"]) == 5 and p2.context["total_count"] == 30


def test_list_search_and_type_filter(client, office_manager):
    DocumentFactory(name="عقد الإيجار", document_type="contract")
    DocumentFactory(name="مذكرة", document_type="pleading")
    client.force_login(office_manager)
    assert client.get(reverse("documents:list"), {"q": "الإيجار"}).context["total_count"] == 1
    assert (
        client.get(reverse("documents:list"), {"document_type": "contract"}).context["total_count"]
        == 1
    )


def test_detail_404_for_missing_and_retired(client, office_manager):
    retired = DocumentFactory(deleted_at=dt.datetime.now(tz=dt.UTC))
    client.force_login(office_manager)
    assert client.get(reverse("documents:detail", args=[999999])).status_code == 404
    assert client.get(reverse("documents:detail", args=[retired.pk])).status_code == 404


# ── upload ─────────────────────────────────────────────────
def test_upload_requires_manage(client, finance_clerk):
    client.force_login(finance_clerk)
    assert client.get(reverse("documents:upload")).status_code == 403
    resp = client.post(
        reverse("documents:upload"), {"file": _upload(), "name": "x", "document_type": "other"}
    )
    assert resp.status_code == 403
    assert not Document.objects.exists()


def test_upload_by_paralegal_creates_and_audits(client, paralegal):
    case = CaseFactory()
    client.force_login(paralegal)
    resp = client.post(
        reverse("documents:upload"),
        {
            "file": _upload("court filing.pdf"),
            "name": "  لائحة الدعوى  ",
            "document_type": "pleading",
            "case": case.pk,
        },
    )
    assert resp.status_code == 302
    doc = Document.objects.get()
    assert doc.name == "لائحة الدعوى"  # trimmed
    assert doc.case_id == case.pk
    assert doc.uploaded_by == paralegal
    assert AuditLog.objects.filter(action=AuditAction.DOCUMENT_UPLOADED).exists()


def test_upload_rejects_disguised_executable(client, office_manager):
    client.force_login(office_manager)
    resp = client.post(
        reverse("documents:upload"),
        {
            "file": SimpleUploadedFile("report.pdf", EXE_BYTES),
            "name": "x",
            "document_type": "other",
        },
    )
    assert resp.status_code == 200  # re-rendered with an error
    assert resp.context["form"].errors
    assert not Document.objects.exists()


def test_upload_prefill_ignores_out_of_scope_ids(client, office_manager):
    client.force_login(office_manager)
    form = client.get(reverse("documents:upload") + "?case=999999&client=abc").context["form"]
    assert form.initial.get("case") is None


def test_upload_mass_assignment_ignores_extra_fields(client, office_manager):
    client.force_login(office_manager)
    client.post(
        reverse("documents:upload"),
        {
            "file": _upload(),
            "name": "y",
            "document_type": "other",
            "sha256": "deadbeef",
            "size": "999999",
            "uploaded_by": 1,
            "deleted_at": "2020-01-01",
        },
    )
    doc = Document.objects.get()
    assert doc.sha256 != "deadbeef"
    assert doc.size == len(MINIMAL_PDF)
    assert doc.deleted_at is None


# ── download (the private path) ────────────────────────────
def test_download_requires_login(client):
    d = DocumentFactory()
    resp = client.get(reverse("documents:download", args=[d.pk]))
    assert resp.status_code == 302


def test_download_streams_as_attachment_and_audits(client, finance_clerk):
    d = DocumentFactory(
        file=SimpleUploadedFile("s.pdf", MINIMAL_PDF), content_type="application/pdf"
    )
    client.force_login(finance_clerk)
    resp = client.get(reverse("documents:download", args=[d.pk]))
    assert resp.status_code == 200
    assert resp["Content-Disposition"].startswith("attachment;")
    assert resp["X-Content-Type-Options"] == "nosniff"
    assert b"".join(resp.streaming_content) == MINIMAL_PDF
    assert AuditLog.objects.filter(
        action=AuditAction.DOCUMENT_DOWNLOADED, entity_id=str(d.pk)
    ).exists()


def test_download_404_for_missing_or_retired(client, office_manager):
    retired = DocumentFactory(deleted_at=dt.datetime.now(tz=dt.UTC))
    client.force_login(office_manager)
    assert client.get(reverse("documents:download", args=[999999])).status_code == 404
    assert client.get(reverse("documents:download", args=[retired.pk])).status_code == 404


def test_download_is_get_only(client, office_manager):
    d = DocumentFactory()
    client.force_login(office_manager)
    assert client.post(reverse("documents:download", args=[d.pk])).status_code == 405


def test_download_404_when_blob_missing(client, office_manager):
    d = DocumentFactory()
    d.file.storage.delete(d.file.name)  # blob vanished out of band
    client.force_login(office_manager)
    resp = client.get(reverse("documents:download", args=[d.pk]))
    assert resp.status_code == 404
    # a phantom download must not be audited
    assert not AuditLog.objects.filter(action=AuditAction.DOCUMENT_DOWNLOADED).exists()


def test_no_public_media_url_for_documents(client, office_manager):
    """The file must not be reachable at a predictable /media/ path, and the
    production documents storage refuses to build a URL at all."""
    from config.settings import base as base_settings
    from documents.storage import PrivateFileSystemStorage

    d = DocumentFactory()
    client.force_login(office_manager)
    # 1. no route serves the documents directory at all
    assert client.get(f"/media/documents/{d.file.name}").status_code == 404
    assert client.get(f"/media/{d.file.name}").status_code == 404
    # 2. the production storage class refuses .url()
    assert (
        base_settings.STORAGES["documents"]["BACKEND"]
        == "documents.storage.PrivateFileSystemStorage"
    )
    with pytest.raises(ValueError):
        PrivateFileSystemStorage(location="/tmp").url("2026/09/abc")


# ── retire ─────────────────────────────────────────────────
def test_retire_is_post_only_and_gated(client, finance_clerk):
    d = DocumentFactory()
    client.force_login(finance_clerk)
    assert client.get(reverse("documents:retire", args=[d.pk])).status_code == 405
    assert client.post(reverse("documents:retire", args=[d.pk])).status_code == 403


def test_retire_by_manager_soft_deletes(client, office_manager):
    d = DocumentFactory()
    client.force_login(office_manager)
    resp = client.post(reverse("documents:retire", args=[d.pk]))
    assert resp.status_code == 302
    d.refresh_from_db()
    assert d.deleted_at is not None


# ── edit ───────────────────────────────────────────────────
def test_edit_has_no_file_field(client, office_manager):
    d = DocumentFactory()
    client.force_login(office_manager)
    form = client.get(reverse("documents:update", args=[d.pk])).context["form"]
    assert "file" not in form.fields


def test_edit_keeps_archived_client_in_picker(client, office_manager):
    from clients.models import ClientStatus
    from clients.tests.factories import ClientFactory

    cl = ClientFactory()
    d = DocumentFactory(client=cl)
    cl.status = ClientStatus.ARCHIVED
    cl.save()
    client.force_login(office_manager)
    form = client.get(reverse("documents:update", args=[d.pk])).context["form"]
    assert cl in list(form.fields["client"].queryset)


# ── case integration ───────────────────────────────────────
def test_case_documents_tab_and_upload_link(client, office_manager):
    case = CaseFactory(status=CaseStatus.CLOSED)
    DocumentFactory(case=case, name="حكم")
    client.force_login(office_manager)
    resp = client.get(reverse("cases:detail", args=[case.pk]), {"tab": "documents"})
    assert resp.status_code == 200
    assert list(resp.context["case_documents"]) != []
    # closed case: uploading a doc via ?case= still works (widened picker)
    form = client.get(reverse("documents:upload") + f"?case={case.pk}").context["form"]
    assert str(form.initial.get("case")) == str(case.pk)
    assert case in list(form.fields["case"].queryset)
