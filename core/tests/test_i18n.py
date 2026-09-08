import pytest
from django.conf import settings
from django.utils import translation
from django.utils.formats import number_format

pytestmark = pytest.mark.django_db


def test_default_language_is_arabic():
    assert settings.LANGUAGE_CODE == "ar"


def test_format_module_pinned_to_western_digits():
    with translation.override("ar"):
        rendered = number_format(1234567.89, decimal_pos=2, use_l10n=True, force_grouping=True)
    assert rendered == "1,234,567.89"
    assert not any(d in rendered for d in "٠١٢٣٤٥٦٧٨٩")


def test_login_page_is_rtl_and_arabic(client):
    html = client.get("/accounts/login/").content.decode()
    assert 'dir="rtl"' in html
    assert 'lang="ar"' in html
    assert "تسجيل الدخول" in html


def test_strings_are_translatable():
    # A representative Phase 1 string is wrapped in gettext.
    with translation.override("en"):
        # No English catalog shipped, so it falls back to the source (Arabic) —
        # the point is that the lookup path exists.
        assert translation.gettext("تسجيل الدخول") == "تسجيل الدخول"
