from django.core.management.base import BaseCommand

from core.messaging.consumer import run_consumer
from users.handlers import handle_group_deleted

QUEUE = "users.group_events"

HANDLERS = {
    "group.deleted": handle_group_deleted,
}


class Command(BaseCommand):
    help = "Écoute les événements RabbitMQ destinés à S2 (group.deleted...)."

    def handle(self, *args, **options):
        run_consumer(QUEUE, HANDLERS)
