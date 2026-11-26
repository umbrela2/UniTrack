import json
import logging
import os

import pika

from .models import ProcessedEvent
from .sync import ENTITY_ALIASES, process_sync_payload

logger = logging.getLogger(__name__)

DEFAULT_RABBITMQ_URL = 'amqp://guest:guest@localhost:5672/'
EXCHANGE_NAME = 'unitrack.events'
QUEUE_NAME = 's6_statistics_queue'
ROUTING_KEYS = ('attendance.#',)

CONTRACT_ENVELOPE_KEYS = ('event_id', 'event_type', 'version', 'source', 'occurred_at', 'data')

CONTRACT_EVENT_BUCKETS = {
    'attendance.recorded.v1': 'presences',
    'attendance.session.started.v1': 'seances',
    'attendance.session.closed.v1': 'seances',
    'attendance.session.not_held.v1': 'seances',
    'attendance.absence_threshold_reached.v1': 'etudiants',
}

FIELD_RENAMES = {
    'student_id': 'etudiant_id',
    'academic_seance_id': 'seance_id',
    'statut': 'statut_presence',
}

STATUS_NORMALIZATION = {
    'present': 'Présent',
    'présent': 'Présent',
    'absent': 'Absent',
    'justifie': 'Justifié',
    'justifié': 'Justifié',
}


def _normalize_status(value):
    if not isinstance(value, str):
        return value
    key = value.strip().lower()
    return STATUS_NORMALIZATION.get(key, value.strip())


def _rename_fields(item):
    renamed = {}
    for key, value in item.items():
        renamed[FIELD_RENAMES.get(key, key)] = value
    if 'statut_presence' in renamed:
        renamed['statut_presence'] = _normalize_status(renamed['statut_presence'])
    return renamed


def _unwrap_contract_envelope(payload):
    """Return (event_id, event_type, data) for a contract envelope, else (None, None, payload)."""
    if not isinstance(payload, dict):
        return None, None, payload
    if not all(key in payload for key in ('event_id', 'event_type')):
        return None, None, payload

    event_id = payload.get('event_id')
    event_type = payload.get('event_type')
    data = payload.get('data')
    if data is None:
        data = {
            key: value
            for key, value in payload.items()
            if key not in CONTRACT_ENVELOPE_KEYS
        }
    return event_id, event_type, data


def _prepare_payload(body, routing_key):
    payload = json.loads(body.decode('utf-8'))

    if isinstance(payload, list):
        return {'event': routing_key, 'data': payload}

    if not isinstance(payload, dict):
        raise ValueError('Le message RabbitMQ doit contenir un objet JSON.')

    event_id, event_type, data = _unwrap_contract_envelope(payload)

    if event_type is not None:
        bucket = CONTRACT_EVENT_BUCKETS.get(event_type)
        if bucket is None:
            entity = event_type.split('.')[0].strip().lower()
            bucket = ENTITY_ALIASES.get(entity)
        if bucket is None:
            raise ValueError(f'Événement contrat non pris en charge : {event_type}.')

        if isinstance(data, dict):
            items = [_rename_fields(data)]
        elif isinstance(data, list):
            items = [_rename_fields(item) for item in data]
        else:
            items = [data]

        return {bucket: items}

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


def _is_duplicate(event_id):
    if not event_id:
        return False
    return ProcessedEvent.objects.filter(event_id=event_id).exists()


def _mark_processed(event_id):
    if not event_id:
        return
    ProcessedEvent.objects.get_or_create(event_id=event_id)


def handle_message(channel, method, properties, body):
    routing_key = method.routing_key
    try:
        payload = json.loads(body.decode('utf-8'))
        event_id, event_type, _data = _unwrap_contract_envelope(payload)

        if event_id is not None and _is_duplicate(event_id):
            logger.info(
                'Événement contrat déjà traité, ignoré (event_id=%s, routing_key=%s).',
                event_id,
                routing_key,
            )
            channel.basic_ack(delivery_tag=method.delivery_tag)
            return

        prepared = _prepare_payload(body, routing_key)
        result = process_sync_payload(prepared)

        if event_id is not None:
            _mark_processed(event_id)

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
