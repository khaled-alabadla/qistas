import pytest
from django.template import Context, Template

pytestmark = pytest.mark.django_db


def render(src: str, **ctx) -> str:
    return Template("{% load qistas %}" + src).render(Context(ctx))


def test_num_wraps_in_bdi_ltr():
    out = render('{% num "C-2026-0001" %}')
    assert out == '<bdi dir="ltr">C-2026-0001</bdi>'


def test_num_formats_decimals_western():
    out = render("{% num value 2 %}", value=12450.5)
    assert "12,450.50" in out
    # Western digits only
    assert not any(d in out for d in "٠١٢٣٤٥٦٧٨٩")


def test_num_empty():
    assert render("{% num value %}", value=None) == ""


def test_can_tag(office_manager, rf):
    req = rf.get("/")
    req.user = office_manager
    out = render('{% can "settings.view" as ok %}{{ ok }}', request=req)
    assert out.strip() == "True"


def test_has_capability_filter(lawyer):
    out = render('{{ user|has_capability:"settings.view" }}', user=lawyer)
    assert out.strip() == "False"
