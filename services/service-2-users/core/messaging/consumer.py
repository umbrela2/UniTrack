"""
Consumer RabbitMQ générique (process séparé : python manage.py consume_events).

- Queue durable, liée à l'exchange topic pour chaque routing key gérée
- ack manuel : le message n'est retiré qu'après traitement réussi
- en cas d'erreur : 1 nouvel essai (requeue), puis le message est écarté
- reconnexion automatique si RabbitMQ redémarre
"""
import json
import logging
import time

import pika
from django.conf import settings
from django.db import close_old_connections

logger = logging.getLogger(__name__)


def _make_callback(handlers):
    def callback(channel, method, properties, body):
        close_old_connections()  # process long : évite les connexions DB périmées
        try:
            message = json.loads(body)
            event_type = message.get("event_type") or method.routing_key
            handler = handlers.get(event_type)
            if handler is None:
                logger.warning("Aucun handler pour %s", event_type)
            else:
                handler(message.get("data") or {}, message)
                logger.info("Traité : %s (%s)", event_type, message.get("event_id"))
            channel.basic_ack(method.delivery_tag)
        except json.JSONDecodeError:
            logger.error("Message non JSON écarté : %r", body[:200])
            channel.basic_ack(method.delivery_tag)
        except Exception:
            logger.exception("Erreur de traitement (routing key %s)", method.routing_key)
            # 1er échec : on remet en file ; 2e échec (redelivered) : on écarte
            channel.basic_nack(method.delivery_tag, requeue=not method.redelivered)

    return callback


def run_consumer(queue, handlers):
    params = pika.URLParameters(settings.RABBITMQ_URL)
    try:
        while True:
            try:
                connection = pika.BlockingConnection(params)
                channel = connection.channel()
                channel.exchange_declare(
                    exchange=settings.RABBITMQ_EXCHANGE, exchange_type="topic", durable=True
                )
                channel.queue_declare(queue=queue, durable=True)
                for routing_key in handlers:
                    channel.queue_bind(
                        queue=queue, exchange=settings.RABBITMQ_EXCHANGE, routing_key=routing_key
                    )
                channel.basic_qos(prefetch_count=1)
                channel.basic_consume(queue=queue, on_message_callback=_make_callback(handlers))
                logger.info("En écoute sur '%s' : %s", queue, ", ".join(handlers))
                channel.start_consuming()
            except pika.exceptions.AMQPConnectionError:
                logger.warning("RabbitMQ indisponible, nouvelle tentative dans 5 s...")
                time.sleep(5)
    except KeyboardInterrupt:
        logger.info("Consumer arrêté.")
