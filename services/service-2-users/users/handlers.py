"""Traitement des événements reçus par S2 (appelés par consume_events)."""
import logging
import uuid

from django.db import transaction

from core.messaging.events import UserEvents
from core.messaging.publisher import publish_user_event

from .models import StudentProfile, User

logger = logging.getLogger(__name__)


def handle_group_deleted(data, message=None):
    """S3 a supprimé un groupe : les étudiants concernés n'ont plus de groupe.
    Idempotent : rejouer le même événement ne change rien."""
    raw_id = data.get("group_id") or data.get("id")
    try:
        group_id = uuid.UUID(str(raw_id))
    except ValueError:
        logger.warning("group.deleted ignoré : group_id invalide (%r)", raw_id)
        return

    with transaction.atomic():
        profiles = StudentProfile.objects.filter(group_id=group_id)
        user_ids = list(profiles.values_list("user_id", flat=True))
        if not user_ids:
            return
        profiles.update(group_id=None)
        # S4 garde une copie du group_id : on prévient avec user.updated
        for user in User.objects.select_related("student_profile", "teacher_profile").filter(
            pk__in=user_ids
        ):
            publish_user_event(UserEvents.UPDATED, user)
    logger.info("Groupe %s supprimé : %d étudiant(s) mis à jour", group_id, len(user_ids))
