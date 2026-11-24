import json
import logging
import threading

import pika
from django.conf import settings
from django.db import transaction

from .events import build_envelope, build_user_payload

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_connection = None
_channel = None


def _reset():
    global _connection, _channel
    try:
        if _connection is not None and _connection.is_open:
            _connection.close()
    except Exception:
        pass
    _connection = None
    _channel = None


def _get_channel():
    global _connection, _channel
    if _connection is None or _connection.is_closed or _channel is None or _channel.is_closed:
        params = pika.URLParameters(settings.RABBITMQ_URL)
        params.socket_timeout = 3
        params.stack_timeout = 3
        _connection = pika.BlockingConnection(params)
        _channel = _connection.channel()
        _channel.exchange_declare(
            exchange=settings.RABBITMQ_EXCHANGE, exchange_type="topic", durable=True
        )
        _channel.confirm_delivery()
    return _channel


def publish(routing_key, data):
    """Publie un événement. Retourne True si RabbitMQ l'a confirmé."""
    message = build_envelope(routing_key, data)
    body = json.dumps(message)
    for attempt in (1, 2):  # 2e essai : la connexion inactive a pu être fermée
        try:
            with _lock:
                channel = _get_channel()
                channel.basic_publish(
                    exchange=settings.RABBITMQ_EXCHANGE,
                    routing_key=routing_key,
                    body=body,
                    properties=pika.BasicProperties(
                        content_type="application/json",
                        delivery_mode=2,  # message persistant
                        message_id=message["event_id"],
                    ),
                )
            logger.info("Événement publié : %s (%s)", routing_key, message["event_id"])
            return True
        except Exception:
            _reset()
            if attempt == 2:
                logger.exception("Échec de publication de %s", routing_key)
    return False


def publish_user_event(event_type, user):
    """Publie l'événement APRÈS le commit de la transaction en cours."""
    data = build_user_payload(user)
    transaction.on_commit(lambda: publish(event_type, data))