from django.apps import AppConfig


class TasksConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "tasks"
    verbose_name = "المهام"

    def ready(self) -> None:
        from tasks import audit  # noqa: F401  (registers models with auditlog)
