"""TOTP + recovery-code helpers (docs/adr/0017)."""

from __future__ import annotations

import qrcode
import qrcode.image.svg
from django.conf import settings
from django_otp.plugins.otp_static.models import StaticDevice, StaticToken
from django_otp.plugins.otp_totp.models import TOTPDevice

TOTP_DEVICE_NAME = "default"
RECOVERY_DEVICE_NAME = "recovery"

# Session key holding the URL to return to after the post-login OTP step.
MFA_NEXT_SESSION_KEY = "_mfa_next"


def get_or_create_unconfirmed_totp(user) -> TOTPDevice:
    device, _created = TOTPDevice.objects.get_or_create(
        user=user, name=TOTP_DEVICE_NAME, defaults={"confirmed": False}
    )
    if device.confirmed:
        # Already set up; caller decides what to do.
        return device
    return device


def qr_svg(data: str) -> str:
    img = qrcode.make(data, image_factory=qrcode.image.svg.SvgPathImage, box_size=10, border=2)
    return img.to_string().decode("utf-8")


def confirmed_totp(user) -> TOTPDevice | None:
    return TOTPDevice.objects.filter(user=user, confirmed=True).first()


def generate_recovery_codes(user, count: int | None = None) -> list[str]:
    count = count or getattr(settings, "MFA_RECOVERY_CODE_COUNT", 10)
    device, _created = StaticDevice.objects.get_or_create(user=user, name=RECOVERY_DEVICE_NAME)
    device.token_set.all().delete()
    codes: list[str] = []
    for _ in range(count):
        token = StaticToken.random_token()
        device.token_set.create(token=token)
        codes.append(token)
    device.confirmed = True
    device.save()
    return codes


def has_mfa(user) -> bool:
    return confirmed_totp(user) is not None
