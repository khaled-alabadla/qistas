from django.apps import AppConfig


class ClientsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "clients"
    verbose_name = "العملاء"

    def ready(self) -> None:
        from clients import audit  # noqa: F401  (registers Client with auditlog)
