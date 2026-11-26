from django.core.management.base import BaseCommand

from attendance.messaging import run_consumer


class Command(BaseCommand):
    help = "Consomme les événements RabbitMQ (academic.seance.*, academic.enrollment.*) – processus 'worker'."

    def handle(self, *args, **opts):
        run_consumer()
