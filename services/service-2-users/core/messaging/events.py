"""
Contrat des événements publiés par S2 (voir docs/events.md).
Exchange : topic, durable. Routing key = type de l'événement.
"""
import uuid
from datetime import datetime, timezone

EVENT_VERSION = 1
SOURCE = "user-management"


class UserEvents:
    CREATED = "user.created"
    UPDATED = "user.updated"
    ACTIVATED = "user.activated"
    DEACTIVATED = "user.deactivated"
    DELETED = "user.deleted"


def _s(value):
    return str(value) if value else None


def build_user_payload(user):
    """Données minimales (loi 18-07) : ni téléphone ni date de naissance."""
    data = {
        "user_id": str(user.id),
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "role": user.role,
        "status": user.status,
        "language": user.language,
        "department_id": _s(user.department_id),
    }
    student = getattr(user, "student_profile", None)
    if student is not None:
        data["student"] = {
            "matricule": student.matricule,
            "group_id": _s(student.group_id),
            "section_id": _s(student.section_id),
        }
    teacher = getattr(user, "teacher_profile", None)
    if teacher is not None:
        data["teacher"] = {"grade": teacher.grade}
    return data


def build_envelope(event_type, data):
    return {
        "event_id": str(uuid.uuid4()),  # les consommateurs s'en servent pour l'idempotence
        "event_type": event_type,
        "version": EVENT_VERSION,
        "source": SOURCE,
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "data": data,
    }
