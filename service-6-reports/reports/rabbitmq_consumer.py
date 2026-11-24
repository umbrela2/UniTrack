import json
import logging
import os

import pika

from .sync import ENTITY_ALIASES, process_sync_payload

logger = logging.getLogger(__name__)

DEFAULT_RABBITMQ_URL = 'amqp://guest:guest@localhost:5672/'
EXCHANGE_NAME = 'unitrack.events'
QUEUE_NAME = 's6_statistics_queue'
ROUTING_KEYS = ('session.*', 'attendance.*')


def _prepare_payload(body, routing_key):
    payload = json.loads(body.decode('utf-8'))

    if isinstance(payload, list):
        return {'event': routing_key, 'data': payload}

    if not isinstance(payload, dict):
        raise ValueError('Le message RabbitMQ doit contenir un objet JSON.')

    has_entity_bucket = any(
        isinstance(key, str) and key.strip().lower() in ENTITY_ALIASES
        for key in payload
    )
    has_event_data = any(
        key in payload for key in ('data', 'payload', 'item')
    )
    has_external_id = 'external_id' in payload
    has_event_name = any(
        key in payload for key in ('event', 'entity', 'type')
    )

    if has_entity_bucket or has_event_data:
        return payload

    if has_event_name and has_external_id:
        return payload

    return {'event': routing_key, 'data': payload}


def handle_message(channel, method, properties, body):
    routing_key = method.routing_key
    try:
        payload = _prepare_payload(body, routing_key)
        result = process_sync_payload(payload)
    except Exception:
        logger.exception(
            'Échec du traitement du message %s (routing_key=%s).',
            method.delivery_tag,
            routing_key,
        )
        channel.basic_nack(
            delivery_tag=method.delivery_tag,
            requeue=False,
        )
        return

    logger.info(
        'Message %s traité (routing_key=%s, total=%s).',
        method.delivery_tag,
        routing_key,
        result['total_processed'],
    )
    channel.basic_ack(delivery_tag=method.delivery_tag)


def run_consumer(url=None, queue=None):
    rabbitmq_url = url or os.getenv('RABBITMQ_URL', DEFAULT_RABBITMQ_URL)
    queue_name = queue or os.getenv('RABBITMQ_QUEUE', QUEUE_NAME)
    exchange_name = os.getenv('RABBITMQ_EXCHANGE', EXCHANGE_NAME)

    parameters = pika.URLParameters(rabbitmq_url)
    parameters.heartbeat = 60
    connection = pika.BlockingConnection(parameters)
    channel = connection.channel()

    channel.exchange_declare(
        exchange=exchange_name,
        exchange_type='topic',
        durable=True,
    )
    channel.queue_declare(queue=queue_name, durable=True)
    for routing_key in ROUTING_KEYS:
        channel.queue_bind(
            queue=queue_name,
            exchange=exchange_name,
            routing_key=routing_key,
        )

    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(
        queue=queue_name,
        on_message_callback=handle_message,
    )

    logger.info(
        'Consommation de %s (exchange=%s) démarrée.',
        queue_name,
        exchange_name,
    )

    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        channel.stop_consuming()
    finally:
        connection.close()
