"""Realistic Arabic demo clients (spec §61). Idempotent."""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from clients.models import Client, ClientStatus, ClientType
from clients.services import allocate_client_number

CO = ClientType.COMPANY
IND = ClientType.INDIVIDUAL

DEMO = [
    {
        "type": CO,
        "company_name": "شركة الوفاق التجارية",
        "registration_number": "562-114-903",
        "phone": "+970-2-2951000",
        "email": "info@alwefaq.ps",
        "city": "رام الله",
        "status": ClientStatus.ACTIVE,
    },
    {
        "type": CO,
        "company_name": "مؤسسة البيادر للمقاولات",
        "registration_number": "562-208-771",
        "phone": "+970-2-2400211",
        "city": "بيت لحم",
        "status": ClientStatus.ACTIVE,
    },
    {
        "type": CO,
        "company_name": "مكتب العدالة للاستشارات",
        "registration_number": "562-330-118",
        "phone": "+970-9-2381444",
        "email": "office@aladala.ps",
        "city": "نابلس",
        "status": ClientStatus.PROSPECT,
    },
    {
        "type": IND,
        "full_name": "محمود أحمد درويش",
        "national_id": "905112233",
        "phone": "+970-599-101010",
        "city": "رام الله",
        "status": ClientStatus.ACTIVE,
    },
    {
        "type": IND,
        "full_name": "سميرة خليل حمدان",
        "national_id": "904778812",
        "phone": "+970-598-224466",
        "email": "s.hamdan@example.ps",
        "city": "الخليل",
        "status": ClientStatus.ACTIVE,
    },
    {
        "type": IND,
        "full_name": "خالد يوسف النجار",
        "national_id": "900334455",
        "phone": "+970-569-778899",
        "city": "جنين",
        "status": ClientStatus.INACTIVE,
    },
    {
        "type": IND,
        "full_name": "رنا عبد الله زهران",
        "national_id": "907665544",
        "phone": "+970-597-556677",
        "city": "طولكرم",
        "status": ClientStatus.ACTIVE,
    },
    {
        "type": CO,
        "company_name": "جمعية الإغاثة الزراعية",
        "registration_number": "562-401-556",
        "phone": "+970-2-2963333",
        "city": "رام الله",
        "status": ClientStatus.ARCHIVED,
    },
]


class Command(BaseCommand):
    help = "Create ~8 realistic Palestinian demo clients (idempotent)."

    @transaction.atomic
    def handle(self, *args, **options):
        created = 0
        for row in DEMO:
            key = "company_name" if row["type"] == ClientType.COMPANY else "full_name"
            if Client.objects.filter(**{key: row[key]}).exists():
                continue
            Client.objects.create(client_number=allocate_client_number(), **row)
            created += 1
        self.stdout.write(self.style.SUCCESS(f"created {created} demo client(s)"))
