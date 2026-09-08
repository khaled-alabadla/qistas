from __future__ import annotations

import factory
from faker import Faker

from clients.models import Client, ClientStatus, ClientType

fake = Faker("ar_AA")


class ClientFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Client

    client_number = factory.Sequence(lambda n: f"CL-2026-{n + 1:04d}")
    type = ClientType.INDIVIDUAL
    full_name = factory.LazyFunction(lambda: fake.name())
    company_name = ""
    phone = factory.Sequence(lambda n: f"+970-599-{n:06d}")
    city = factory.LazyFunction(lambda: fake.city())
    status = ClientStatus.ACTIVE


class CompanyClientFactory(ClientFactory):
    type = ClientType.COMPANY
    full_name = ""
    company_name = factory.Sequence(lambda n: f"شركة الاختبار {n}")
    registration_number = factory.Sequence(lambda n: f"562-000-{n:03d}")
