from django.apps import AppConfig


class DocumentsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "documents"
    verbose_name = "المستندات"

    def ready(self) -> None:
        from documents import audit  # noqa: F401  (registers models with auditlog)
