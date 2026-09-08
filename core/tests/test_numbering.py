import pytest
from django.db import connection

from core.numbering import NumberSequence, format_reference, next_number
from core.tests.utils import run_concurrently

pytestmark = pytest.mark.django_db


def test_sequential_allocation():
    assert next_number("case") == 1
    assert next_number("case") == 2
    assert next_number("case", period="2026") == 1  # separate counter


def test_format_reference():
    assert format_reference("C", 7, period="2026") == "C-2026-0007"
    assert format_reference("CL", 42) == "CL-0042"


@pytest.mark.postgres
@pytest.mark.django_db(transaction=True)
def test_concurrent_allocation_has_no_duplicates():
    if connection.vendor != "postgresql":
        pytest.skip("needs real row locking")

    n = 20

    def allocate():
        from django.db import connection as conn

        try:
            return next_number("invoice", period="2026")
        finally:
            conn.close()

    results = run_concurrently(allocate, n)
    errors = [r for r in results if isinstance(r, Exception)]
    assert not errors, errors
    assert sorted(results) == list(range(1, n + 1))
    assert NumberSequence.objects.get(scope="invoice", period="2026").last_value == n
