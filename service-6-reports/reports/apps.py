import sys

from django.apps import AppConfig

SKIP_COMMANDS = {'migrate', 'test'}


class ReportsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'reports'

    def ready(self):
        if any(command in sys.argv for command in SKIP_COMMANDS):
            return

        from .consul_client import register_service

        register_service()
