"""Logique métier de S4 (appel, présences, clôture, seuils, séances non assurées).

Règles de gestion couvertes : RG1 (une saisie par séance), RG2 (code valide 5 min,
séance « en cours »), RG3 (groupe), RG4 (Présent/Absent), RG12 (seuil d'absences),
RG15 (géolocalisation optionnelle), FP5, FP6, FP7, FP12.
"""
import hmac
import logging
import math
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.utils import timezone

from . import events
from .exceptions import DomainError
from .models import (AttendanceSettings, Enrollment, Presence, PresenceMode, PresenceStatus, Seance,
                     SeanceStatus)

log = logging.getLogger(__name__)


# ----------------------------------------------------------------- utilitaires
def seance_event_data(s):
    return {
        "seance_id": s.id, "academic_seance_id": s.academic_seance_id,
        "module_id": s.module_id, "module_intitule": s.module_intitule,
        "group_id": s.group_id, "group_label": s.group_label,
        "enseignant_id": s.enseignant_id, "enseignant_nom": s.enseignant_nom,
        "salle_nom": s.salle_nom, "date_seance": s.date_seance.isoformat(),
        "heure_debut": s.heure_debut.strftime("%H:%M"), "heure_fin": s.heure_fin.strftime("%H:%M"),
        "type_seance": s.type_seance,
    }


def _new_code():
    while True:
        code = f"{secrets.randbelow(10 ** 6):06d}"
        if not Seance.objects.filter(statut=SeanceStatus.EN_COURS, code_presence=code).exists():
            return code


def _lock(seance_id):
    try:
        return Seance.objects.select_for_update().get(pk=seance_id)
    except Seance.DoesNotExist:
        raise DomainError("seance_not_found", "Séance introuvable.", 404)


def _assert_owner(seance, user):
    if seance.enseignant_id != user.id:
        raise DomainError("forbidden", "Cette séance n'est pas affectée à cet enseignant.", 403)


def _haversine_m(lat1, lon1, lat2, lon2):
    r = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def level_for(count, cfg):
    if count >= cfg.threshold_critical:
        return "rouge"
    if count >= cfg.threshold_warning:
        return "orange"
    return "vert"


# ------------------------------------------------------------------ enseignant
@transaction.atomic
def start_seance(seance_id, user):
    """UC-ENS-01 : démarre la séance et génère le code temporaire (FP5)."""
    s = _lock(seance_id)
    _assert_owner(s, user)
    if s.statut != SeanceStatus.PLANIFIEE:
        raise DomainError("invalid_state", f"Séance déjà {s.get_statut_display().lower()}.", 409)
    now = timezone.now()
    if s.date_seance != timezone.localdate():
        raise DomainError("not_today", "Seules les séances du jour peuvent être démarrées.", 400)
    if now < s.start_dt - timedelta(minutes=settings.START_EARLY_MINUTES):
        raise DomainError("too_early", "Il est trop tôt pour démarrer cette séance.", 409)
    if now > s.end_dt:
        raise DomainError("too_late", "L'horaire de la séance est dépassé.", 409)
    cfg = AttendanceSettings.get()
    s.statut = SeanceStatus.EN_COURS
    s.started_at = now
    s.code_presence = _new_code()
    s.code_expires_at = now + timedelta(minutes=cfg.code_validity_minutes)
    s.save()
    events.emit(events.RK_SESSION_STARTED, seance_event_data(s))
    return s


@transaction.atomic
def regenerate_code(seance_id, user):
    s = _lock(seance_id)
    _assert_owner(s, user)
    if s.statut != SeanceStatus.EN_COURS:
        raise DomainError("session_not_active", "La séance n'est pas en cours.", 409)
    cfg = AttendanceSettings.get()
    s.code_presence = _new_code()
    s.code_expires_at = timezone.now() + timedelta(minutes=cfg.code_validity_minutes)
    s.save(update_fields=["code_presence", "code_expires_at", "updated_at"])
    return s


@transaction.atomic
def manual_set_presence(seance_id, user, student_id, statut):
    """UC-ENS-03 / FP7 : appel manuel pendant la séance active."""
    s = _lock(seance_id)
    _assert_owner(s, user)
    if s.statut != SeanceStatus.EN_COURS:
        raise DomainError("session_not_active", "L'appel manuel n'est possible que pendant la séance active.", 409)
    if statut not in PresenceStatus.values:
        raise DomainError("invalid_status", "Statut attendu : PRESENT ou ABSENT.", 400)
    if not Enrollment.objects.filter(student_id=student_id, group_id=s.group_id).exists():
        raise DomainError("student_not_in_group", "Cet étudiant n'appartient pas au groupe.", 404)
    p, _ = Presence.objects.update_or_create(
        seance=s, student_id=student_id,
        defaults={"statut": statut, "mode": PresenceMode.MANUEL,
                  "date_enregistrement": timezone.now(), "modifie_par": user.id})
    events.emit(events.RK_RECORDED, {**seance_event_data(s), "student_id": student_id,
                                     "statut": statut, "mode": PresenceMode.MANUEL})
    return p


@transaction.atomic
def close_seance(seance_id, actor=None):
    """Clôture : les étudiants sans présence deviennent ABSENTS, puis contrôle des seuils.
    actor=None → clôture automatique par le système."""
    s = _lock(seance_id)
    if actor is not None:
        _assert_owner(s, actor)
    if s.statut != SeanceStatus.EN_COURS:
        raise DomainError("session_not_active", "La séance n'est pas en cours.", 409)
    now = timezone.now()
    enrolled = list(Enrollment.objects.filter(group_id=s.group_id))
    done = set(Presence.objects.filter(seance=s).values_list("student_id", flat=True))
    Presence.objects.bulk_create(
        [Presence(seance=s, student_id=e.student_id, statut=PresenceStatus.ABSENT, mode=PresenceMode.AUTO,
                  date_enregistrement=now) for e in enrolled if e.student_id not in done],
        ignore_conflicts=True)
    s.statut = SeanceStatus.CLOTUREE
    s.closed_at = now
    s.code_presence = ""
    s.code_expires_at = None
    s.save()

    absent_ids = list(Presence.objects.filter(seance=s, statut=PresenceStatus.ABSENT)
                      .values_list("student_id", flat=True))
    n_present = Presence.objects.filter(seance=s, statut=PresenceStatus.PRESENT).count()
    _check_thresholds(s, absent_ids, {e.student_id: e for e in enrolled})
    events.emit(events.RK_SESSION_CLOSED, {
        **seance_event_data(s), "closed_by": getattr(actor, "id", "system"),
        "present_count": n_present, "absent_count": len(absent_ids), "absent_student_ids": absent_ids})
    return s


def _check_thresholds(seance, absent_ids, enrol_by_id):
    """RG12 : alerte quand un étudiant ATTEINT le seuil d'absences dans un module."""
    if not absent_ids:
        return
    cfg = AttendanceSettings.get()
    levels = {cfg.threshold_warning: "orange", cfg.threshold_critical: "rouge"}
    rows = (Presence.objects.filter(student_id__in=absent_ids, statut=PresenceStatus.ABSENT,
                                    seance__module_id=seance.module_id)
            .values("student_id").annotate(n=Count("id")))
    for row in rows:
        level = levels.get(row["n"])
        if not level:
            continue
        e = enrol_by_id.get(row["student_id"])
        events.emit(events.RK_THRESHOLD, {
            "student_id": row["student_id"],
            "student_email": e.email if e else "",
            "student_name": f"{e.prenom} {e.nom}".strip() if e else "",
            "module_id": seance.module_id, "module_intitule": seance.module_intitule,
            "group_id": seance.group_id, "absences_count": row["n"], "level": level,
            "threshold": cfg.threshold_warning if level == "orange" else cfg.threshold_critical,
            "seance_id": seance.id, "notify_admin": True})


# -------------------------------------------------------------------- étudiant
@transaction.atomic
def check_in(seance_id, user, code, latitude=None, longitude=None):
    """UC-ETU-01 / FP6 : enregistrement de la présence par saisie du code."""
    s = _lock(seance_id)
    if s.statut != SeanceStatus.EN_COURS:
        raise DomainError("session_not_active", "La séance n'est pas en cours.", 409)
    if not Enrollment.objects.filter(student_id=user.id, group_id=s.group_id).exists():     # RG3
        raise DomainError("not_in_group", "Vous n'appartenez pas au groupe de cette séance.", 403)
    if Presence.objects.filter(seance=s, student_id=user.id).exists():                      # RG1
        raise DomainError("already_recorded", "Présence déjà enregistrée pour cette séance.", 409)
    now = timezone.now()
    if s.code_expires_at is None or now > s.code_expires_at:                                # RG2
        raise DomainError("code_expired", "Le code a expiré : demandez-en un nouveau à l'enseignant.", 410)
    if not hmac.compare_digest(str(code or "").strip(), s.code_presence):
        raise DomainError("invalid_code", "Code incorrect.", 400)
    cfg = AttendanceSettings.get()
    if cfg.geo_check_enabled and cfg.geo_latitude is not None:                              # RG15
        if latitude is None or longitude is None:
            raise DomainError("location_required", "La localisation est requise pour cette séance.", 400)
        if _haversine_m(float(latitude), float(longitude), cfg.geo_latitude, cfg.geo_longitude) > cfg.geo_radius_m:
            raise DomainError("out_of_range", "Vous êtes trop loin de la salle.", 403)
    try:
        with transaction.atomic():
            p = Presence.objects.create(seance=s, student_id=user.id, statut=PresenceStatus.PRESENT,
                                        mode=PresenceMode.CODE, date_enregistrement=now)
    except IntegrityError:                                                                  # double clic concurrent
        raise DomainError("already_recorded", "Présence déjà enregistrée pour cette séance.", 409)
    events.emit(events.RK_RECORDED, {**seance_event_data(s), "student_id": user.id,
                                     "statut": PresenceStatus.PRESENT, "mode": PresenceMode.CODE})
    return p


def student_summary(student_id, module_id=None, date_from=None, date_to=None):
    """UC-ETU-02 : présences/absences par module + niveau d'alerte (FP09)."""
    cfg = AttendanceSettings.get()
    qs = Presence.objects.filter(student_id=student_id).select_related("seance")
    if module_id:
        qs = qs.filter(seance__module_id=module_id)
    if date_from:
        qs = qs.filter(seance__date_seance__gte=date_from)
    if date_to:
        qs = qs.filter(seance__date_seance__lte=date_to)
    rows = (qs.values("seance__module_id", "seance__module_intitule")
            .annotate(presents=Count("id", filter=Q(statut=PresenceStatus.PRESENT)),
                      absents=Count("id", filter=Q(statut=PresenceStatus.ABSENT)))
            .order_by("seance__module_intitule"))
    modules = []
    for r in rows:
        total = r["presents"] + r["absents"]
        modules.append({
            "module_id": r["seance__module_id"], "module_intitule": r["seance__module_intitule"],
            "presents": r["presents"], "absents": r["absents"], "total": total,
            "taux_assiduite": round(100 * r["presents"] / total, 1) if total else 100.0,
            "niveau_alerte": level_for(r["absents"], cfg)})
    return {"seuils": {"orange": cfg.threshold_warning, "rouge": cfg.threshold_critical}, "modules": modules}


# ------------------------------------------------------- tâches automatiques
def declare_missed_sessions(now=None):
    """FP12 / UC-SYS-02 : séance jamais démarrée → enseignant absent, séance non assurée.
    Les étudiants ne sont PAS comptés absents (aucune ligne Presence créée)."""
    now = now or timezone.now()
    grace = timedelta(minutes=settings.TEACHER_ABSENCE_GRACE_MINUTES)
    declared = 0
    candidates = Seance.objects.filter(statut=SeanceStatus.PLANIFIEE, date_seance__lte=timezone.localdate()) \
        .values_list("id", flat=True)
    for sid in list(candidates):
        with transaction.atomic():
            s = _lock(sid)
            if s.statut != SeanceStatus.PLANIFIEE:
                continue
            ref = s.end_dt if settings.TEACHER_ABSENCE_REFERENCE == "end" else s.start_dt
            if now <= ref + grace:
                continue
            s.statut = SeanceStatus.NON_ASSUREE
            s.declared_absent_at = now
            s.save()
            events.emit(events.RK_SESSION_NOT_HELD, {**seance_event_data(s), "notify_admin": True})
            declared += 1
    return declared


def auto_close_stale_sessions(now=None):
    now = now or timezone.now()
    limit = timedelta(minutes=settings.AUTO_CLOSE_GRACE_MINUTES)
    closed = 0
    for s in Seance.objects.filter(statut=SeanceStatus.EN_COURS, date_seance__lte=timezone.localdate()):
        if now > s.end_dt + limit:
            try:
                close_seance(s.id, actor=None)
                closed += 1
            except DomainError:
                pass
    return closed
