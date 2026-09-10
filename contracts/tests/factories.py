from __future__ import annotations

import datetime as dt

import factory

from clients.tests.factories import ClientFactory
from contracts.models import Contract, ContractStatus, ContractType, Currency


class ContractFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Contract

    contract_number = factory.Sequence(lambda n: f"CT-2026-{n + 1:04d}")
    title = factory.Sequence(lambda n: f"عقد اختبار {n}")
    contract_type = ContractType.ENGAGEMENT
    client = factory.SubFactory(ClientFactory)
    status = ContractStatus.DRAFT
    start_date = factory.LazyFunction(lambda: dt.date.today() - dt.timedelta(days=30))
    end_date = factory.LazyFunction(lambda: dt.date.today() + dt.timedelta(days=180))
    value = factory.LazyFunction(lambda: 10000)
    currency = Currency.ILS
