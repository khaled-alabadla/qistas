from django.apps import AppConfig


class HearingsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "hearings"
    verbose_name = "الجلسات"

    def ready(self) -> None:
        from hearings import audit  # noqa: F401  (registers models with auditlog)
