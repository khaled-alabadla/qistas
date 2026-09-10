"""
Local fixtures: in this app the plain ``user`` / ``user_factory`` yield staff
members who hold ``notifications.view`` (i.e. belong to a role group). A
group-less account is not a Qistas staff member and has no inbox.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def user_factory(db, groups):
    from core.tests.factories import UserFactory

    def make(**kwargs):
        u = UserFactory(**kwargs)
        u.groups.add(groups["lawyer"])
        return u

    return make


@pytest.fixture
def user(user_factory):
    return user_factory()
