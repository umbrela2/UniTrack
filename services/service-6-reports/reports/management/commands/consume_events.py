from django.core.management.base import BaseCommand, CommandError

from reports.rabbitmq_consumer import run_consumer


class Command(BaseCommand):
    help = (
        'Consomme les événements session.* et attendance.* depuis RabbitMQ '
        'et synchronise les statistiques.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--url',
            default=None,
            help='URL AMQP (défaut : variable RABBITMQ_URL).',
        )
        parser.add_argument(
            '--queue',
            default=None,
            help='Nom de la file (défaut : s6_statistics_queue).',
        )

    def handle(self, *args, **options):
        self.stdout.write('Démarrage du consommateur RabbitMQ...')
        try:
            run_consumer(url=options['url'], queue=options['queue'])
        except Exception as exc:
            raise CommandError(
                f'Consommateur RabbitMQ arrêté : {exc}'
            ) from exc
