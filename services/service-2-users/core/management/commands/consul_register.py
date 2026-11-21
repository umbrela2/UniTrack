from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core.consul_client import register, service_id


class Command(BaseCommand):
    help = "Enregistre S2 dans Consul (avec health check sur /health/)."

    def handle(self, *args, **options):
        try:
            register()
        except Exception as exc:
            raise CommandError(
                f"Consul inaccessible ({settings.CONSUL_HOST}:{settings.CONSUL_PORT}) : {exc}"
            )
        self.stdout.write(self.style.SUCCESS(f"Service enregistré : {service_id()}"))
