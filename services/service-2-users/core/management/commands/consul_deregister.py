from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core.consul_client import deregister, service_id


class Command(BaseCommand):
    help = "Retire S2 de Consul."

    def handle(self, *args, **options):
        try:
            deregister()
        except Exception as exc:
            raise CommandError(
                f"Consul inaccessible ({settings.CONSUL_HOST}:{settings.CONSUL_PORT}) : {exc}"
            )
        self.stdout.write(self.style.SUCCESS(f"Service retiré : {service_id()}"))
