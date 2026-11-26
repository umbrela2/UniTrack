"""RabbitMQ : publication (outbox) et consommation des événements."""
import json
import logging
import time

import pika
from django.conf import settings
from django.db import connection, transaction
from django.utils import timezone

from .models import OutboxEvent, ProcessedMessage

log = logging.getLogger(__name__)

BINDINGS = ["academic.seance.*", "academic.enrollment.*"]


def _params():
    return pika.URLParameters(settings.RABBITMQ_URL)


def declare_topology(ch):
    ch.exchange_declare(exchange=settings.EVENTS_EXCHANGE, exchange_type="topic", durable=True)
    ch.exchange_declare(exchange=settings.DLX_EXCHANGE, exchange_type="fanout", durable=True)


def flush_outbox(batch_size=100):
    """Publie les événements en attente. Retourne le nombre d'événements publiés."""
    with transaction.atomic():
        qs = OutboxEvent.objects.filter(published_at__isnull=True).order_by("created_at")
        if connection.features.has_select_for_update_skip_locked:
            qs = qs.select_for_update(skip_locked=True)        # plusieurs workers possibles
        events = list(qs[:batch_size])
        if not events:
            return 0
        try:
            conn = pika.BlockingConnection(_params())
        except Exception as exc:  # noqa: BLE001
            log.warning("RabbitMQ indisponible (%s) : %d événement(s) restent dans l'outbox", exc, len(events))
            return 0
        sent = 0
        try:
            ch = conn.channel()
            declare_topology(ch)
            ch.confirm_delivery()
            for ev in events:
                try:
                    ch.basic_publish(
                        exchange=settings.EVENTS_EXCHANGE, routing_key=ev.routing_key,
                        body=json.dumps(ev.payload).encode(),
                        properties=pika.BasicProperties(content_type="application/json", delivery_mode=2,
                                                        message_id=str(ev.id), type=ev.routing_key))
                    ev.published_at = timezone.now()
                    ev.save(update_fields=["published_at"])
                    sent += 1
                except Exception as exc:  # noqa: BLE001
                    ev.attempts += 1
                    ev.last_error = str(exc)[:500]
                    ev.save(update_fields=["attempts", "last_error"])
                    break
        finally:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass
        return sent


def run_consumer():
    """Boucle de consommation avec reconnexion automatique."""
    from .handlers import dispatch
    while True:
        try:
            conn = pika.BlockingConnection(_params())
            ch = conn.channel()
            declare_topology(ch)
            dlq = settings.CONSUMER_QUEUE + ".dlq"
            ch.queue_declare(queue=dlq, durable=True)
            ch.queue_bind(queue=dlq, exchange=settings.DLX_EXCHANGE)
            ch.queue_declare(queue=settings.CONSUMER_QUEUE, durable=True,
                             arguments={"x-dead-letter-exchange": settings.DLX_EXCHANGE})
            for rk in BINDINGS:
                ch.queue_bind(queue=settings.CONSUMER_QUEUE, exchange=settings.EVENTS_EXCHANGE, routing_key=rk)
            ch.basic_qos(prefetch_count=20)

            def on_message(channel, method, props, body):
                try:
                    payload = json.loads(body)
                    mid = props.message_id or payload.get("event_id") or f"{method.routing_key}:{hash(body)}"
                    if ProcessedMessage.objects.filter(pk=mid).exists():
                        return channel.basic_ack(method.delivery_tag)        # doublon : déjà traité
                    with transaction.atomic():
                        dispatch(method.routing_key, payload.get("data", payload))
                        ProcessedMessage.objects.create(message_id=mid)
                    channel.basic_ack(method.delivery_tag)
                except Exception:  # noqa: BLE001
                    log.exception("Échec du traitement de %s → dead-letter queue", method.routing_key)
                    channel.basic_nack(method.delivery_tag, requeue=False)

            ch.basic_consume(queue=settings.CONSUMER_QUEUE, on_message_callback=on_message)
            log.info("Consommateur démarré sur %s (%s)", settings.CONSUMER_QUEUE, BINDINGS)
            ch.start_consuming()
        except (pika.exceptions.AMQPError, OSError) as exc:
            log.warning("Connexion RabbitMQ perdue (%s) – nouvelle tentative dans 5 s", exc)
            time.sleep(5)
