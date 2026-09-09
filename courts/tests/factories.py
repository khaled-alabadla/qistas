from __future__ import annotations

import factory

from courts.models import Court, CourtType


class CourtFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Court
        django_get_or_create = ("name", "city")

    name = factory.Sequence(lambda n: f"محكمة بداية {n}")
    type = CourtType.FIRST_INSTANCE
    city = "رام الله"
