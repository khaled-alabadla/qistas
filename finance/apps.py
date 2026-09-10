from django.apps import AppConfig


class FinanceConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "finance"
    verbose_name = "المالية"

    def ready(self) -> None:
        from finance import audit  # noqa: F401  (registers models with auditlog)
