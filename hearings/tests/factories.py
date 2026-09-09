from __future__ import annotations

from datetime import timedelta

import factory
from django.utils import timezone

from cases.tests.factories import CaseFactory
from hearings.models import Hearing, HearingStatus, HearingType


class HearingFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Hearing

    case = factory.SubFactory(CaseFactory)
    scheduled_at = factory.LazyFunction(lambda: timezone.now() + timedelta(days=7))
    hearing_type = HearingType.FIRST_SESSION
    status = HearingStatus.SCHEDULED
