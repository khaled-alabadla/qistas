from __future__ import annotations

import factory

from cases.models import Case, CasePriority, CaseStatus, CaseType
from clients.tests.factories import ClientFactory
from courts.tests.factories import CourtFactory

__all__ = ["CaseFactory", "CaseTypeFactory", "CourtFactory"]


class CaseTypeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = CaseType
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"نوع {n}")
    is_active = True


class CaseFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Case

    case_number = factory.Sequence(lambda n: f"CS-2026-{n + 1:04d}")
    title = factory.Sequence(lambda n: f"قضية اختبار {n}")
    type = factory.SubFactory(CaseTypeFactory)
    client = factory.SubFactory(ClientFactory)
    status = CaseStatus.NEW
    priority = CasePriority.MEDIUM
