import os
import sys
from django.apps import AppConfig


class AcademicsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "academics"

    def ready(self):
        if any(cmd in sys.argv for cmd in ("test", "makemigrations", "migrate", "collectstatic")):
            return
        if os.environ.get("RUN_MAIN") == "true" or os.getenv("CONSUL_FORCE_REGISTER") == "true":
            from .consul_client import register_in_consul
            register_in_consul()
