import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import Permission

from accounts.admin import UserAdmin
from accounts.models import User
from audit.models import AuditAction, AuditLog

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin_request(rf, user_factory):
    req = rf.post("/admin/accounts/user/")
    req.user = user_factory(is_staff=True, is_superuser=True)
    # message framework needs storage on the request
    from django.contrib.messages.storage.fallback import FallbackStorage

    req.session = {}
    req._messages = FallbackStorage(req)
    return req


def test_issue_temp_password_sets_flag_and_audits(admin_request, user_factory):
    target = user_factory()
    old_hash = target.password
    ma = UserAdmin(User, AdminSite())
    ma.issue_temp_password(admin_request, User.objects.filter(pk=target.pk))

    target.refresh_from_db()
    assert target.must_change_password is True
    assert target.password != old_hash
    assert AuditLog.objects.filter(
        action=AuditAction.USER_TEMP_PASSWORD, entity_id=str(target.pk)
    ).exists()


def test_action_permission_gate():
    ma = UserAdmin(User, AdminSite())

    class Req:
        pass

    req = Req()

    class WithPerm:
        def has_perm(self, p):
            return p == "accounts.issue_temp_password"

    class NoPerm:
        def has_perm(self, p):
            return False

    req.user = WithPerm()
    assert ma.has_issue_temp_password_permission(req) is True
    req.user = NoPerm()
    assert ma.has_issue_temp_password_permission(req) is False


def test_permission_exists_on_model():
    assert Permission.objects.filter(codename="issue_temp_password").exists()
