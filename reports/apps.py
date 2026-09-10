from __future__ import annotations

from django.apps import AppConfig


class ReportsConfig(AppConfig):
    """Reports — a read/export layer over the existing domains (docs/adr/0034).

    Owns **no models**: every figure is an aggregate or a bounded, capability-
    scoped slice of `cases` / `clients` / `hearings` / `tasks` / `finance`,
    always through those domains' own `for_user()` managers and selectors.
    """

    name = "reports"
    verbose_name = "التقارير"
