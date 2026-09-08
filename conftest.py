"""Pytest fixtures shared across the suite."""

from __future__ import annotations

import pytest
from django.contrib.auth.models import Group


@pytest.fixture(autouse=True)
def _enforce_scoping(settings):
    """Make the object-scoping DEBUG guard active in every test (docs/adr/0019)."""
    settings.QISTAS_ENFORCE_SCOPING = True


@pytest.fixture
def groups(db) -> dict[str, Group]:
    from accounts.management.commands.sync_roles import GROUPS

    return {name: Group.objects.get_or_create(name=name)[0] for name in GROUPS}


@pytest.fixture
def synced_roles(db) -> None:
    from django.core.management import call_command

    call_command("sync_roles", verbosity=0)


@pytest.fixture
def user_factory(db):
    from core.tests.factories import UserFactory

    return UserFactory


@pytest.fixture
def user(db):
    from core.tests.factories import UserFactory

    return UserFactory()


@pytest.fixture
def office_manager(db, groups):
    from core.tests.factories import UserFactory

    u = UserFactory()
    u.groups.add(groups["office_manager"])
    return u


@pytest.fixture
def lawyer(db, groups):
    from core.tests.factories import UserFactory

    u = UserFactory()
    u.groups.add(groups["lawyer"])
    return u


@pytest.fixture
def logged_in_client(client, user):
    client.force_login(user)
    return client
