import pytest
from django.test import override_settings
from django.urls import reverse
from django_otp.plugins.otp_static.models import StaticDevice
from django_otp.plugins.otp_totp.models import TOTPDevice

pytestmark = pytest.mark.django_db


def _totp_now(device: TOTPDevice) -> str:
    from django_otp.oath import TOTP

    totp = TOTP(device.bin_key, device.step, device.t0, device.digits, device.drift)
    return format(totp.token(), f"0{device.digits}d")


def test_setup_page_offers_qr_and_secret(client, user):
    client.force_login(user)
    resp = client.get(reverse("accounts:mfa_setup"))
    assert resp.status_code == 200
    assert b"<svg" in resp.content
    device = TOTPDevice.objects.get(user=user)
    assert device.confirmed is False


def test_activate_with_valid_token_confirms_and_issues_recovery_codes(client, user):
    client.force_login(user)
    client.get(reverse("accounts:mfa_setup"))
    device = TOTPDevice.objects.get(user=user)
    resp = client.post(reverse("accounts:mfa_activate"), {"token": _totp_now(device)})
    assert resp.status_code == 200
    device.refresh_from_db()
    assert device.confirmed is True
    recovery = StaticDevice.objects.get(user=user, name="recovery")
    assert recovery.token_set.count() == 10


def test_activate_with_bad_token_does_not_confirm(client, user):
    client.force_login(user)
    client.get(reverse("accounts:mfa_setup"))
    resp = client.post(reverse("accounts:mfa_activate"), {"token": "000000"})
    assert resp.status_code == 200
    assert TOTPDevice.objects.get(user=user).confirmed is False


def test_login_with_confirmed_device_requires_second_step(client, user):
    client.force_login(user)
    client.get(reverse("accounts:mfa_setup"))
    device = TOTPDevice.objects.get(user=user)
    client.post(reverse("accounts:mfa_activate"), {"token": _totp_now(device)})
    client.logout()

    resp = client.post(
        reverse("accounts:login"),
        {"username": user.email, "password": "correct-horse-staple-11"},
    )
    assert resp.status_code == 302
    assert resp["Location"] == reverse("accounts:mfa_token")

    # Rule 1: until the OTP step is done, every other page bounces back to it.
    bounced = client.get(reverse("core:landing"))
    assert bounced.status_code == 302
    assert bounced["Location"] == reverse("accounts:mfa_token")

    # Complete the second step with a recovery code (the just-issued TOTP token
    # is in the same time window and would be rejected as a replay).
    recovery = StaticDevice.objects.get(user=user, name="recovery")
    code = recovery.token_set.first().token
    resp2 = client.post(reverse("accounts:mfa_token"), {"token": code})
    assert resp2.status_code == 302

    # Now landing is reachable.
    assert client.get(reverse("core:landing")).status_code == 200


def test_enrolled_user_cannot_skip_otp_step(client, user):
    """A user who set up MFA must pass the OTP step even with global enforcement off."""
    client.force_login(user)
    client.get(reverse("accounts:mfa_setup"))
    device = TOTPDevice.objects.get(user=user)
    client.post(reverse("accounts:mfa_activate"), {"token": _totp_now(device)})
    client.logout()
    client.post(
        reverse("accounts:login"),
        {"username": user.email, "password": "correct-horse-staple-11"},
    )
    # Try to jump straight to a normal page — denied, redirected to the OTP step.
    resp = client.get(reverse("core:settings"))
    assert resp.status_code == 302
    assert resp["Location"] == reverse("accounts:mfa_token")


@override_settings(REQUIRE_MFA=False)
def test_enforcement_off_by_default(client, user):
    client.force_login(user)
    assert client.get(reverse("core:landing")).status_code == 200


@override_settings(REQUIRE_MFA=True)
def test_enforcement_when_setting_on_redirects_to_setup(client, user):
    client.force_login(user)
    resp = client.get(reverse("core:landing"))
    assert resp.status_code == 302
    assert resp["Location"] == reverse("accounts:mfa_setup")
