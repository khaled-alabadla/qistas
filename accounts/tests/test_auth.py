import pytest
from django.urls import reverse

from core.tests.utils import assert_login_required

pytestmark = pytest.mark.django_db


def test_login_success(client, user):
    resp = client.post(
        reverse("accounts:login"),
        {"username": user.email, "password": "correct-horse-staple-11"},
    )
    assert resp.status_code == 302
    assert client.session.get("_auth_user_id") == str(user.pk)


def test_login_wrong_password(client, user):
    resp = client.post(
        reverse("accounts:login"),
        {"username": user.email, "password": "nope"},
    )
    assert resp.status_code == 200
    assert "_auth_user_id" not in client.session
    assert "غير صحيحة" in resp.content.decode()


def test_login_inactive_user(client, user_factory):
    u = user_factory(is_active=False)
    resp = client.post(
        reverse("accounts:login"),
        {"username": u.email, "password": "correct-horse-staple-11"},
    )
    assert "_auth_user_id" not in client.session
    assert resp.status_code == 200


def test_logout_get_does_not_end_session(client, user):
    client.force_login(user)
    # Django 5.x LogoutView is POST-only; a GET must not log the user out.
    client.get(reverse("accounts:logout"))
    assert "_auth_user_id" in client.session


def test_logout_post_ends_session(client, user):
    client.force_login(user)
    resp = client.post(reverse("accounts:logout"))
    assert resp.status_code in (200, 302)
    assert "_auth_user_id" not in client.session


def test_landing_requires_login(client):
    assert_login_required(client, "core:landing")


def test_password_change_requires_auth(client):
    assert_login_required(client, "accounts:password_change")


def test_password_change_clears_must_change_flag(client, user_factory):
    u = user_factory()
    u.must_change_password = True
    u.save()
    client.force_login(u)
    resp = client.post(
        reverse("accounts:password_change"),
        {
            "old_password": "correct-horse-staple-11",
            "new_password1": "brand-new-passphrase-42",
            "new_password2": "brand-new-passphrase-42",
        },
    )
    assert resp.status_code == 302
    u.refresh_from_db()
    assert u.must_change_password is False


def test_password_reset_flow_sends_email(client, user, mailoutbox):
    resp = client.post(reverse("accounts:password_reset"), {"email": user.email})
    assert resp.status_code == 302
    assert len(mailoutbox) == 1
    assert user.email in mailoutbox[0].to
    assert "قِسطاس" in mailoutbox[0].subject


def test_email_is_lowercased_on_create(user_factory):
    u = user_factory(email="MixedCase@Maktab.PS")
    assert u.email == "mixedcase@maktab.ps"


def test_email_login_is_case_insensitive_on_create(db):
    from core.tests.factories import UserFactory

    UserFactory(email="a@b.ps")
    # manager normalises; a second create with different case collides
    with pytest.raises(Exception):  # noqa: B017 - IntegrityError/ValidationError
        UserFactory(email="A@B.PS")
