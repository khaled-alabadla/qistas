from django.apps import AppConfig


class AuditConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "audit"
    verbose_name = "سجل التدقيق"

    def ready(self) -> None:
        from audit import signals

        signals.register()
