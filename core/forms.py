"""Shared form helpers."""

from __future__ import annotations

from django.db.models import QuerySet


def with_current_choice(queryset: QuerySet, current_pk) -> QuerySet:
    """Widen a picker ``queryset`` to also include the row ``current_pk`` (the
    value an edit form's instance already holds), so narrowing the queryset to
    "selectable" rows never silently drops or locks an existing FK once that
    related row is deactivated / archived (cf. buglog bug-041).

    Both sides are forced ``.distinct()`` before the union so it stays lazy and
    never trips ``QuerySet.__or__``'s "cannot combine a unique query with a
    non-unique query" error when the base carries a join-induced ``.distinct()``
    (e.g. ``groups__name__in``). DISTINCT on a primary-key picker is harmless.
    """
    if not current_pk:
        return queryset
    extra = queryset.model._default_manager.filter(pk=current_pk)
    return queryset.distinct() | extra.distinct()
