import logging

import pytest

from core.sensitive import SensitiveDataFilter, redact, scrub_text

pytestmark = pytest.mark.django_db


def _record(msg, args=()):
    return logging.LogRecord("t", logging.INFO, __file__, 1, msg, args, None)


def test_redact_mapping():
    out = redact({"password": "hunter2", "city": "Hebron"})
    assert out["password"] == "***"
    assert out["city"] == "Hebron"


def test_scrub_text_key_value_forms():
    assert scrub_text("token=abc123 ok") == "token=*** ok"
    assert scrub_text('{"secret": "xyz"}') == '{"secret": "***"}'
    assert scrub_text("national_id: 999888777") == "national_id: ***"
    assert scrub_text("plain message") == "plain message"


def test_filter_scrubs_positional_args():
    f = SensitiveDataFilter()
    rec = _record("auth token=%s for user", ("s3cr3t",))
    f.filter(rec)
    assert "s3cr3t" not in rec.getMessage()
    assert "***" in rec.getMessage()


def test_filter_scrubs_mapping_args():
    f = SensitiveDataFilter()
    rec = _record("login %(password)s", ({"password": "pw"},))
    f.filter(rec)
    assert "pw" not in rec.getMessage()
