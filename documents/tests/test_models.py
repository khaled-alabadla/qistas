import datetime as dt

import pytest

from documents.models import Document
from documents.tests.factories import DocumentFactory

pytestmark = pytest.mark.django_db


def test_for_user_denies_anon_allows_authed(user):
    DocumentFactory.create_batch(2)
    assert Document.objects.for_user(None).count() == 0
    assert Document.objects.for_user(user).count() == 2


def test_alive_excludes_retired():
    live = DocumentFactory()
    DocumentFactory(deleted_at=dt.datetime.now(tz=dt.UTC))
    assert list(Document.objects.alive()) == [live]


def test_no_delete_permission():
    assert "delete" not in Document._meta.default_permissions


def test_download_filename_is_sanitised():
    d = DocumentFactory.build(original_filename='../../etc/passwd\n"; rm -rf /.pdf')
    safe = d.download_filename
    assert "/" not in safe and "\n" not in safe and '"' not in safe


def test_download_filename_falls_back():
    d = DocumentFactory.build(original_filename="", name="")
    assert d.download_filename == "document"


def test_search_field_set_and_trgm_in_sync():
    from importlib import import_module

    from documents.models import SEARCH_FIELDS

    mod = import_module("documents.migrations.0002_document_search_indexes")
    assert tuple(sorted(mod.TRGM_COLUMNS)) == tuple(sorted(SEARCH_FIELDS))
