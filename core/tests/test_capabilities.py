import pytest

from core.permissions.capabilities import (
    Capability,
    Group,
    can,
    capabilities_for,
)

pytestmark = pytest.mark.django_db


def test_anonymous_has_no_capabilities(client):
    from django.contrib.auth.models import AnonymousUser

    assert capabilities_for(AnonymousUser()) == frozenset()
    assert can(AnonymousUser(), Capability.DASHBOARD_VIEW) is False


def test_superuser_has_all(user_factory):
    su = user_factory(is_superuser=True, is_staff=True)
    for cap in Capability:
        assert can(su, cap)


def test_office_manager_truth_table(office_manager):
    for cap in (
        Capability.DASHBOARD_VIEW,
        Capability.SETTINGS_VIEW,
        Capability.AUDIT_VIEW,
        Capability.USERS_MANAGE,
    ):
        assert can(office_manager, cap), cap


def test_lawyer_truth_table(lawyer):
    assert can(lawyer, Capability.DASHBOARD_VIEW)
    assert can(lawyer, Capability.NOTIFICATIONS_VIEW)
    assert not can(lawyer, Capability.SETTINGS_VIEW)
    assert not can(lawyer, Capability.AUDIT_VIEW)
    assert not can(lawyer, Capability.USERS_MANAGE)


def test_multi_group_union(user_factory, groups):
    u = user_factory()
    u.groups.add(groups[Group.LAWYER], groups[Group.FINANCE_CLERK])
    caps = capabilities_for(u)
    assert Capability.DASHBOARD_VIEW in caps
    # neither lawyer nor finance_clerk grants settings in Phase 1
    assert Capability.SETTINGS_VIEW not in caps


def test_plain_user_no_groups(user):
    assert capabilities_for(user) == frozenset()
