import pytest
from django.contrib.auth.models import Group
from django.urls import reverse

from audit.models import AuditAction, AuditLog

pytestmark = pytest.mark.django_db


def test_login_and_logout_are_logged(client, user):
    client.post(
        reverse("accounts:login"),
        {"username": user.email, "password": "correct-horse-staple-11"},
    )
    client.post(reverse("accounts:logout"))
    actions = set(AuditLog.objects.values_list("action", flat=True))
    assert AuditAction.LOGIN in actions
    assert AuditAction.LOGOUT in actions


def test_failed_login_is_logged(client, user):
    client.post(reverse("accounts:login"), {"username": user.email, "password": "wrong"})
    assert AuditLog.objects.filter(action=AuditAction.LOGIN_FAILED).exists()


def test_user_creation_is_logged(user_factory):
    u = user_factory()
    assert AuditLog.objects.filter(action=AuditAction.USER_CREATED, entity_id=str(u.pk)).exists()


def test_group_membership_change_is_logged(user, groups):
    before = AuditLog.objects.filter(action=AuditAction.GROUPS_CHANGED).count()
    user.groups.add(Group.objects.get(name="lawyer"))
    entries = AuditLog.objects.filter(action=AuditAction.GROUPS_CHANGED)
    assert entries.count() == before + 1
    latest = entries.order_by("-created_at").first()
    assert "lawyer" in latest.changes.get("groups", [])
    assert latest.entity_id == str(user.pk)


def test_group_clear_is_logged_with_action(user, groups):
    user.groups.add(Group.objects.get(name="lawyer"))
    user.groups.clear()
    latest = (
        AuditLog.objects.filter(action=AuditAction.GROUPS_CHANGED).order_by("-created_at").first()
    )
    assert latest.changes["action"] == "post_clear"


def test_reverse_side_group_change_names_the_user(user, groups):
    lawyer = Group.objects.get(name="lawyer")
    lawyer.user_set.add(user)  # reverse side
    latest = (
        AuditLog.objects.filter(action=AuditAction.GROUPS_CHANGED).order_by("-created_at").first()
    )
    assert latest.entity_id == str(user.pk)
    assert "lawyer" in latest.changes.get("groups", [])
