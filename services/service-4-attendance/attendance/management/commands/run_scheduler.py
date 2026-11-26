import logging
import time

from django.conf import settings
from django.core.management.base import BaseCommand

from attendance import messaging, services

log = logging.getLogger(__name__)


class Command(BaseCommand):
    help = ("Worker périodique : (1) publie l'outbox sur RabbitMQ, (2) déclare les enseignants absents (FP12), "
            "(3) clôture automatiquement les séances oubliées. --once pour un seul passage (cron).")

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")

    def handle(self, *args, **opts):
        last_check = 0.0
        while True:
            now = time.monotonic()
            if now - last_check >= settings.SCHEDULER_INTERVAL_SECONDS or opts["once"]:
                n = services.declare_missed_sessions()
                c = services.auto_close_stale_sessions()
                if n or c:
                    log.info("Scheduler : %d séance(s) non assurée(s), %d clôture(s) automatique(s)", n, c)
                last_check = now
            published = messaging.flush_outbox()
            if published:
                log.info("Outbox : %d événement(s) publié(s)", published)
            if opts["once"]:
                return
            time.sleep(settings.OUTBOX_INTERVAL_SECONDS)
