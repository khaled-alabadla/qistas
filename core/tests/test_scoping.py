"""Object-level authorization framework tests (docs/adr/0019)."""

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.views.generic import DetailView, ListView

from core.permissions.mixins import ScopedDetailMixin, ScopedListMixin
from core.querysets import UnscopedQuerysetError, assert_scoped
from core.tests.testapp.models import ScopedThing

pytestmark = pytest.mark.django_db


@pytest.fixture
def things(user_factory):
    a = user_factory()
    b = user_factory()
    ta = ScopedThing.objects.create(name="A-owned", owner=a)
    tb = ScopedThing.objects.create(name="B-owned", owner=b)
    return {"a": a, "b": b, "ta": ta, "tb": tb}


def test_for_user_filters_to_owner(things):
    qs = ScopedThing.objects.for_user(things["a"])
    assert list(qs) == [things["ta"]]


def test_for_user_is_marked_scoped(things):
    qs = ScopedThing.objects.for_user(things["a"])
    assert getattr(qs, "_is_scoped", False) is True
    assert_scoped(qs)  # must not raise


def test_default_manager_is_not_scoped(things):
    qs = ScopedThing.objects.all()
    assert getattr(qs, "_is_scoped", False) is False
    with pytest.raises(UnscopedQuerysetError):
        assert_scoped(qs)


def test_base_for_user_not_implemented():
    from core.querysets import ScopedQuerySet

    class Bare(ScopedQuerySet):
        pass

    with pytest.raises(NotImplementedError):
        Bare(model=ScopedThing).for_user(None)


def _req(rf, user):
    r = rf.get("/x/")
    r.user = user
    return r


def test_scoped_list_mixin_returns_only_owned(rf, things):
    class V(ScopedListMixin, ListView):
        model = ScopedThing

    view = V()
    view.request = _req(rf, things["a"])
    view.kwargs = {}
    assert list(view.get_queryset()) == [things["ta"]]


def test_scoped_detail_denies_other_users_object_with_403(rf, things):
    from django.core.exceptions import PermissionDenied

    class V(ScopedDetailMixin, DetailView):
        model = ScopedThing

    view = V()
    view.request = _req(rf, things["a"])
    view.kwargs = {"pk": things["tb"].pk}  # belongs to b
    with pytest.raises(PermissionDenied):
        view.get_object()


def test_scoped_detail_allows_own_object(rf, things):
    class V(ScopedDetailMixin, DetailView):
        model = ScopedThing

    view = V()
    view.request = _req(rf, things["a"])
    view.kwargs = {"pk": things["ta"].pk}
    assert view.get_object() == things["ta"]


def test_mixin_requires_for_user_manager(rf, user):
    from django.contrib.auth.models import Group  # ordinary manager, no for_user

    class V(ScopedListMixin, ListView):
        model = Group

    view = V()
    view.request = _req(rf, user)
    view.kwargs = {}
    with pytest.raises(ImproperlyConfigured):
        view.get_queryset()
