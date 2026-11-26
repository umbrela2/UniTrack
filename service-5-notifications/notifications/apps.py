from django.apps import AppConfig
import os
from django.apps import AppConfig

class NotificationsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'notifications'

    def ready(self):
        if os.environ.get('RUN_MAIN') == 'true':
            from .consul_registry import register_service
            register_service()

class NotificationsConfig(AppConfig):
    name = 'notifications'
