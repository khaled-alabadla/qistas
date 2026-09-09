from django.apps import AppConfig


class CourtsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "courts"
    verbose_name = "المحاكم"

    def ready(self) -> None:
        from courts import audit  # noqa: F401  (registers models with auditlog)
