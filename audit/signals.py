"""Auth-event receivers (docs/adr/0020).

`register()` is called from ``AuditConfig.ready()``.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.signals import (
    user_logged_in,
    user_logged_out,
    user_login_failed,
)
from django.db.models.signals import m2m_changed, post_save
from django.dispatch import receiver

from audit.events import log_event
from audit.models import AuditAction

User = get_user_model()


@receiver(user_logged_in)
def _on_login(sender, request, user, **kwargs):
    log_event(request, AuditAction.LOGIN, actor=user, obj=user)


@receiver(user_logged_out)
def _on_logout(sender, request, user, **kwargs):
    if user is not None:
        log_event(request, AuditAction.LOGOUT, actor=user, obj=user)


@receiver(user_login_failed)
def _on_login_failed(sender, credentials, request=None, **kwargs):
    username = str((credentials or {}).get("username") or "")
    log_event(
        request,
        AuditAction.LOGIN_FAILED,
        entity_type="accounts.user",
        object_repr=username[:200],
    )


@receiver(post_save, sender=User)
def _on_user_created(sender, instance, created, **kwargs):
    if created:
        log_event(None, AuditAction.USER_CREATED, obj=instance)


@receiver(m2m_changed, sender=User.groups.through)
def _on_groups_changed(sender, instance, action, pk_set, reverse=False, **kwargs):
    if action not in {"post_add", "post_remove", "post_clear"}:
        return
    from django.contrib.auth.models import Group

    # `instance` is a User on the forward side, a Group on the reverse side.
    # `pk_set` holds the *other* model's PKs (None on post_clear).
    if reverse:
        users = list(User.objects.filter(pk__in=pk_set or []))
        for user in users or [None]:
            _log_group_change(user, action, [instance.name] if action != "post_clear" else [])
        return

    if action == "post_clear":
        _log_group_change(instance, action, [])
    else:
        names = list(Group.objects.filter(pk__in=pk_set or []).values_list("name", flat=True))
        _log_group_change(instance, action, names)


def _log_group_change(user, action: str, group_names: list[str]) -> None:
    log_event(
        None,
        AuditAction.GROUPS_CHANGED,
        obj=user,
        entity_type="accounts.user" if user is None else None,
        changes={"action": action, "groups": group_names},
    )


def register() -> None:
    """Placeholder for signal wiring that needs late imports.

    Lockout events are audited in ``accounts.views.axes_lockout_response`` (the
    ``AXES_LOCKOUT_CALLABLE``), which is the single point every lockout passes
    through — so no axes signal is connected here.
    """
    return
