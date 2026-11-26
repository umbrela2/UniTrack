"""Contrats d'événements publiés par S4 (versionnés : suffixe .v1)."""
import json
import uuid

from django.core.serializers.json import DjangoJSONEncoder
from django.utils import timezone

from .models import OutboxEvent

RK_RECORDED = "attendance.recorded.v1"
RK_THRESHOLD = "attendance.absence_threshold_reached.v1"
RK_SESSION_STARTED = "attendance.session.started.v1"
RK_SESSION_CLOSED = "attendance.session.closed.v1"
RK_SESSION_NOT_HELD = "attendance.session.not_held.v1"


def emit(routing_key, data):
    """À appeler DANS la transaction métier : écrit l'événement dans l'outbox."""
    event_id = uuid.uuid4()
    envelope = {
        "event_id": str(event_id),
        "event_type": routing_key,
        "version": 1,
        "source": "attendance-service",
        "occurred_at": timezone.now().isoformat(),
        "data": data,
    }
    payload = json.loads(json.dumps(envelope, cls=DjangoJSONEncoder))
    return OutboxEvent.objects.create(id=event_id, routing_key=routing_key, payload=payload)
