import pytest
from django.core.exceptions import ImproperlyConfigured, PermissionDenied
from django.http import HttpResponse
from django.views.generic import View

from core.permissions.decorators import require_capability
from core.permissions.mixins import CapabilityRequiredMixin

pytestmark = pytest.mark.django_db


class _View(CapabilityRequiredMixin, View):
    required_capability = "settings.view"

    def get(self, request):
        return HttpResponse("ok")


def _req(rf, user):
    r = rf.get("/")
    r.user = user
    return r


def test_mixin_allows_holder(rf, office_manager):
    resp = _View.as_view()(_req(rf, office_manager))
    assert resp.status_code == 200


def test_mixin_denies_non_holder(rf, lawyer):
    with pytest.raises(PermissionDenied):
        _View.as_view()(_req(rf, lawyer))


def test_mixin_requires_configuration(rf, office_manager):
    class Bad(CapabilityRequiredMixin, View):
        def get(self, request):
            return HttpResponse("x")

    with pytest.raises(ImproperlyConfigured):
        Bad.as_view()(_req(rf, office_manager))


def test_decorator_denies_non_holder(rf, lawyer):
    @require_capability("settings.view")
    def view(request):
        return HttpResponse("ok")

    with pytest.raises(PermissionDenied):
        view(_req(rf, lawyer))


def test_decorator_allows_holder(rf, office_manager):
    @require_capability("settings.view")
    def view(request):
        return HttpResponse("ok")

    assert view(_req(rf, office_manager)).status_code == 200
