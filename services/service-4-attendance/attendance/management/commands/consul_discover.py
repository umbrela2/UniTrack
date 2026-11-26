from django.core.management.base import BaseCommand

from attendance import consul


class Command(BaseCommand):
    help = "Démonstration de la découverte Consul : python manage.py consul_discover auth-service"

    def add_arguments(self, parser):
        parser.add_argument("service")

    def handle(self, *args, **opts):
        instances = consul.discover(opts["service"])
        if not instances:
            self.stdout.write(self.style.WARNING("Aucune instance saine."))
        for i in instances:
            self.stdout.write(f"{i['id']} → http://{i['address']}:{i['port']}")
