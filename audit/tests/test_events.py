import pytest
from django.test import RequestFactory

from audit.events import log_event

pytestmark = pytest.mark.django_db


def test_log_event_captures_actor_ip_and_ua(user):
    rf = RequestFactory()
    req = rf.get("/", HTTP_USER_AGENT="pytest-UA", REMOTE_ADDR="203.0.113.9")
    req.user = user

    entry = log_event(req, "other", obj=user, changes={"first_name": ["a", "b"]})
    assert entry.actor == user
    assert entry.ip_address == "203.0.113.9"
    assert entry.user_agent == "pytest-UA"
    assert entry.entity_type == "accounts.user"
    assert entry.entity_id == str(user.pk)


def test_log_event_redacts_sensitive_changes(user, monkeypatch):
    import core.sensitive as sensitive

    monkeypatch.setattr(sensitive, "SENSITIVE_FIELDS", {"national_id"})
    rf = RequestFactory()
    req = rf.get("/")
    req.user = user
    entry = log_event(req, "other", changes={"national_id": ["111", "222"], "city": ["x", "y"]})
    assert entry.changes["national_id"] == "***"
    assert entry.changes["city"] == ["x", "y"]


def test_log_event_without_request():
    entry = log_event(None, "other", entity_type="x.y", object_repr="z")
    assert entry.actor is None
    assert entry.ip_address is None


def test_forwarded_for_is_not_trusted_by_default(user, settings):
    settings.AUDIT_TRUST_XFF = False
    rf = RequestFactory()
    req = rf.get("/", HTTP_X_FORWARDED_FOR="1.2.3.4", REMOTE_ADDR="10.0.0.1")
    req.user = user
    entry = log_event(req, "other")
    assert entry.ip_address == "10.0.0.1"


def test_forwarded_for_used_when_trusted(user, settings):
    settings.AUDIT_TRUST_XFF = True
    rf = RequestFactory()
    req = rf.get("/", HTTP_X_FORWARDED_FOR="1.2.3.4, 10.0.0.1", REMOTE_ADDR="10.0.0.1")
    req.user = user
    entry = log_event(req, "other")
    assert entry.ip_address == "1.2.3.4"


def test_invalid_ip_is_dropped(user, settings):
    settings.AUDIT_TRUST_XFF = True
    rf = RequestFactory()
    req = rf.get("/", HTTP_X_FORWARDED_FOR="not-an-ip", REMOTE_ADDR="10.0.0.1")
    req.user = user
    entry = log_event(req, "other")
    assert entry.ip_address == "10.0.0.1"
