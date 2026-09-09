"""End-to-end HTTP smoke for the Phase 6 surface (documents)."""

import pytest
from django.urls import reverse

from cases.tests.factories import CaseFactory
from clients.tests.factories import ClientFactory
from documents.tests.factories import DocumentFactory

pytestmark = pytest.mark.django_db


def test_phase6_pages_render(client, office_manager):
    client.force_login(office_manager)
    case = CaseFactory()
    cl = ClientFactory()
    doc = DocumentFactory(case=case, client=cl)
    urls = [
        reverse("documents:list"),
        reverse("documents:list") + "?q=&document_type=pleading",
        reverse("documents:upload"),
        reverse("documents:upload") + f"?case={case.pk}&client={cl.pk}",
        reverse("documents:detail", args=[doc.pk]),
        reverse("documents:update", args=[doc.pk]),
        reverse("cases:detail", args=[case.pk]) + "?tab=documents",
        reverse("clients:detail", args=[cl.pk]),
    ]
    for url in urls:
        assert client.get(url).status_code == 200, url
    # the download streams
    resp = client.get(reverse("documents:download", args=[doc.pk]))
    assert resp.status_code == 200
