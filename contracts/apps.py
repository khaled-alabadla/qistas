from django.apps import AppConfig


class ContractsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "contracts"
    verbose_name = "العقود"

    def ready(self) -> None:
        from contracts import audit  # noqa: F401  (registers models with auditlog)
