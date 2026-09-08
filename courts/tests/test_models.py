import pytest
from django.db import IntegrityError

from courts.models import Court, CourtType

pytestmark = pytest.mark.django_db


def test_str_with_and_without_city():
    name = "محكمة بداية رام الله"
    assert str(Court(name=name, city="رام الله")) == f"{name} - رام الله"
    assert str(Court(name="محكمة العدل العليا")) == "محكمة العدل العليا"


def test_name_city_unique():
    Court.objects.create(name="محكمة صلح", city="نابلس", type=CourtType.CONCILIATION)
    with pytest.raises(IntegrityError):
        Court.objects.create(name="محكمة صلح", city="نابلس", type=CourtType.CONCILIATION)


def test_seed_command_is_idempotent():
    from django.core.management import call_command

    call_command("seed_demo_courts", verbosity=0)
    n = Court.objects.count()
    call_command("seed_demo_courts", verbosity=0)
    assert Court.objects.count() == n and n >= 7
