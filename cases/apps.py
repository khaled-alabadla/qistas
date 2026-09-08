from django.apps import AppConfig


class CasesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "cases"
    verbose_name = "القضايا"

    def ready(self) -> None:
        from cases import audit  # noqa: F401  (registers models with auditlog)
