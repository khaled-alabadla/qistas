"""
The one place notifications are created or mutated (docs/adr/0035, spec Phase 11
§6). Views and the reminder scan call in here; nothing writes ``Notification``
directly.

* :func:`notify` — idempotent single create, keyed on ``(recipient, dedupe_key)``.
* :func:`bulk_notify` — the reminder-scan path: many rows, two queries, no
  duplicates.
* :func:`mark_read` / :func:`mark_all_read` — recipient-scoped lifecycle.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from django.utils import timezone

from notifications.models import Notification


@dataclass(frozen=True)
class NotificationSpec:
    """A notification to (idempotently) create for one recipient."""

    recipient_id: int
    category: str
    title: str
    body: str
    dedupe_key: str
    url: str = ""
    entity_type: str = ""
    entity_id: str = ""


def notify(
    *,
    recipient,
    category: str,
    title: str,
    body: str,
    dedupe_key: str,
    url: str = "",
    entity_type: str = "",
    entity_id: str = "",
) -> tuple[Notification, bool]:
    """Create the notification unless ``(recipient, dedupe_key)`` already exists.

    Returns ``(notification, created)``. Safe to call repeatedly — the unique
    constraint is the backstop if two callers race.
    """
    obj, created = Notification.objects.get_or_create(
        recipient=recipient,
        dedupe_key=dedupe_key,
        defaults={
            "category": str(category),
            "title": title,
            "body": body,
            "url": url,
            "entity_type": entity_type,
            "entity_id": str(entity_id or ""),
        },
    )
    return obj, created


def bulk_notify(specs: Iterable[NotificationSpec]) -> int:
    """Create every spec that does not already exist. Two queries total
    (existing-key lookup + one ``bulk_create``); no per-row or per-recipient
    query. Returns the number of rows actually inserted.
    """
    specs = list(specs)
    if not specs:
        return 0

    keys = {s.dedupe_key for s in specs}
    existing = {
        (r_id, key)
        for r_id, key in Notification.objects.filter(dedupe_key__in=keys).values_list(
            "recipient_id", "dedupe_key"
        )
    }
    seen: set[tuple[int, str]] = set()
    rows: list[Notification] = []
    for s in specs:
        pair = (s.recipient_id, s.dedupe_key)
        if pair in existing or pair in seen:
            continue
        seen.add(pair)
        rows.append(
            Notification(
                recipient_id=s.recipient_id,
                category=str(s.category),
                title=s.title,
                body=s.body,
                url=s.url,
                entity_type=s.entity_type,
                entity_id=str(s.entity_id or ""),
                dedupe_key=s.dedupe_key,
            )
        )
    if not rows:
        return 0
    # ignore_conflicts: a concurrent scan may have inserted a row between the
    # lookup and here — the UniqueConstraint makes that a no-op, not an error.
    created = Notification.objects.bulk_create(rows, ignore_conflicts=True)
    return len(created)


def mark_read(*, user, notification_id) -> bool:
    """Mark one of ``user``'s notifications read. Returns ``True`` if this call
    changed it. A notification that is not the user's is simply not found —
    never a permission error that confirms it exists (docs/adr/0035 §4)."""
    obj = Notification.objects.for_user(user).filter(pk=notification_id).first()
    if obj is None:
        return False
    return obj.mark_read()


def mark_all_read(*, user) -> int:
    """Mark every unread notification of ``user`` read. Returns the count."""
    return Notification.objects.for_user(user).unread().update(read_at=timezone.now())
