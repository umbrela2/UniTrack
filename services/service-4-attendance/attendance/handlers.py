"""Traitement des événements publiés par S3 (Academic) pour alimenter les copies locales.
Tous les handlers sont idempotents (upsert)."""
import datetime as dt
import logging

from .models import Enrollment, Presence, Seance, SeanceStatus

log = logging.getLogger(__name__)


def _t(value):
    return dt.time.fromisoformat(value)


def seance_upserted(d):
    defaults = {
        "module_id": str(d["module"]["id"]), "module_intitule": d["module"].get("name", ""),
        "semestre": d["module"].get("semester", ""),
        "group_id": str(d["group"]["id"]), "group_label": d["group"].get("label", ""),
        "enseignant_id": str(d["teacher"]["id"]), "enseignant_nom": d["teacher"].get("name", ""),
        "salle_id": str(d.get("room", {}).get("id", "")), "salle_nom": d.get("room", {}).get("name", ""),
        "date_seance": dt.date.fromisoformat(d["date"]), "heure_debut": _t(d["start_time"]),
        "heure_fin": _t(d["end_time"]), "type_seance": d.get("type", "TD"),
    }
    obj, created = Seance.objects.get_or_create(academic_seance_id=str(d["id"]), defaults=defaults)
    if not created:
        if obj.statut != SeanceStatus.PLANIFIEE:
            log.warning("Séance %s déjà %s : mise à jour du planning ignorée", obj.id, obj.statut)
            return
        for k, v in defaults.items():
            setattr(obj, k, v)
        obj.save()


def seance_deleted(d):
    s = Seance.objects.filter(academic_seance_id=str(d["id"]), statut=SeanceStatus.PLANIFIEE).first()
    if s and not Presence.objects.filter(seance=s).exists():
        s.delete()


def enrollment_upserted(d):
    Enrollment.objects.update_or_create(
        student_id=str(d["student_id"]), group_id=str(d["group_id"]),
        defaults={"matricule": d.get("matricule", ""), "nom": d.get("last_name", ""),
                  "prenom": d.get("first_name", ""), "email": d.get("email", "")})


def enrollment_removed(d):
    Enrollment.objects.filter(student_id=str(d["student_id"]), group_id=str(d["group_id"])).delete()


ROUTES = {
    "academic.seance.upserted.v1": seance_upserted,
    "academic.seance.deleted.v1": seance_deleted,
    "academic.enrollment.upserted.v1": enrollment_upserted,
    "academic.enrollment.removed.v1": enrollment_removed,
}


def dispatch(routing_key, data):
    handler = ROUTES.get(routing_key)
    if handler is None:
        log.info("Événement ignoré : %s", routing_key)
        return
    handler(data)
