from django.apps import AppConfig


class AttendanceConfig(AppConfig):
    name = "attendance"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from . import schema  # noqa: F401  (extension OpenAPI pour le JWT)
