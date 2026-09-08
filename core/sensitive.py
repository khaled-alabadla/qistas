"""
Central registry of highly-sensitive field names + redaction helpers
(docs/adr/0009).

Rules for anything in ``SENSITIVE_FIELDS``:
* never written to logs (the ``SensitiveDataFilter`` below scrubs log records),
* audit logs record "changed" without old/new values (see ``audit.events``),
* excluded from global search / trigram indexes,
* surfaced in the UI only where the feature strictly requires it.

Phase 1 has no domain models, so the set is empty. Every phase that adds a
sensitive field adds its name here in the same change.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from typing import Any

SENSITIVE_FIELDS: set[str] = {
    # Phase 2 — Client identity numbers (docs/adr/0009). Gated in the UI and
    # masked / redacted everywhere: audit diffs, logs, search.
    "national_id",
    "registration_number",
}

# Substrings that mark a value sensitive even without an exact field match.
_SENSITIVE_HINTS = ("password", "secret", "token", "national_id", "authorization")

REDACTED = "***"


def is_sensitive(key: str) -> bool:
    key_l = key.lower()
    return key in SENSITIVE_FIELDS or any(h in key_l for h in _SENSITIVE_HINTS)


def redact(data: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return a copy of ``data`` with sensitive values replaced by ``REDACTED``."""
    if not data:
        return {}
    return {k: (REDACTED if is_sensitive(k) else v) for k, v in data.items()}


def _all_keys() -> tuple[str, ...]:
    return tuple({*SENSITIVE_FIELDS, *_SENSITIVE_HINTS})


def _kv_pattern() -> re.Pattern[str]:
    keys = "|".join(re.escape(k) for k in _all_keys())
    # key=value  |  key: value  |  "key": "value"
    return re.compile(rf'(?i)(["\']?(?:{keys})["\']?\s*[:=]\s*["\']?)([^"\'\s,;&}}]+)')


def scrub_text(text: str) -> str:
    if not text:
        return text
    return _kv_pattern().sub(lambda m: m.group(1) + REDACTED, text)


class SensitiveDataFilter(logging.Filter):
    """Defensive logging filter — scrubs `key=value` pairs for sensitive keys from
    the fully-rendered message, plus mapping and positional args. NOT a substitute
    for simply never logging sensitive values (docs/adr/0009)."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            rendered = record.getMessage()
        except Exception:
            return True
        scrubbed = scrub_text(rendered)
        if scrubbed != rendered:
            record.msg = scrubbed
            record.args = ()
        elif isinstance(record.args, Mapping):
            record.args = redact(record.args)
        return True
