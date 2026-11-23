"""Evenements asynchrones via RabbitMQ (Exigence WAMS 2.4 & CDC 2.3)."""
import json
import logging
import urllib.request

from django.conf import settings

log = logging.getLogger(__name__)


def _publish_rabbitmq(event_type, payload):
    if not getattr(settings, "RABBITMQ_ENABLED", True):
        return False
    try:
        import pika
    except ImportError:
        log.warning("Librairie pika non installee.")
        return False

    credentials = pika.PlainCredentials(
        settings.RABBITMQ_USER,
        settings.RABBITMQ_PASSWORD,
    )
    params = pika.ConnectionParameters(
        host=settings.RABBITMQ_HOST,
        port=settings.RABBITMQ_PORT,
        virtual_host=settings.RABBITMQ_VHOST,
        credentials=credentials,
        connection_attempts=2,
        retry_delay=1,
        socket_timeout=3,
    )
    message = json.dumps({"event": event_type, "data": payload})
    try:
        connection = pika.BlockingConnection(params)
        channel = connection.channel()
        channel.exchange_declare(
            exchange=settings.RABBITMQ_EXCHANGE,
            exchange_type="topic",
            durable=True,
        )
        channel.basic_publish(
            exchange=settings.RABBITMQ_EXCHANGE,
            routing_key=event_type,
            body=message.encode("utf-8"),
            properties=pika.BasicProperties(
                content_type="application/json",
                delivery_mode=2,
            ),
        )
        connection.close()
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("Echec publication RabbitMQ (%s): %s", event_type, exc)
        return False


def send_event(event_type, payload):
    sent_mq = _publish_rabbitmq(event_type, payload)

    url = getattr(settings, "NOTIFICATION_URL", "")
    if not url:
        if not sent_mq:
            log.info("Evenement %s (broker non disponible): %s", event_type, payload)
        return sent_mq

    body = json.dumps({"event": event_type, "data": payload}).encode()
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        urllib.request.urlopen(req, timeout=3)
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("Echec fallback HTTP %s: %s", event_type, exc)
        return sent_mq
