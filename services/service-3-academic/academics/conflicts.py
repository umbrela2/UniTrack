"""Detection de conflits de planification (UC-SYS-01, FP3).

Controle applicatif qui renvoie un type + une description claire.
La contrainte PostgreSQL (constraints.py) garantit la meme regle en BD.
"""
from .models import Seance

TYPE_ENSEIGNANT = "ENSEIGNANT"
TYPE_SALLE = "SALLE"
TYPE_GROUPE = "GROUPE"


def _fmt(s):
    return (
        f"{s.date_seance:%d/%m/%Y} de {s.heure_debut:%H:%M} "
        f"a {s.heure_fin:%H:%M} ({s.module.intitule})"
    )


def detect_conflicts(*, date_seance, heure_debut, heure_fin,
                     enseignant_id, salle, groupe, exclude_id=None):
    """Retourne la liste des conflits : [{type, description, seance_id}]."""
    qs = (
        Seance.objects.filter(
            date_seance=date_seance,
            heure_debut__lt=heure_fin,   # chevauchement strict [debut, fin)
            heure_fin__gt=heure_debut,
        )
        .exclude(statut=Seance.Statut.ANNULEE)
        .select_related("module", "salle", "groupe")
    )
    if exclude_id:
        qs = qs.exclude(pk=exclude_id)

    conflits = []
    if enseignant_id:
        for s in qs.filter(enseignant_id=enseignant_id):
            conflits.append({
                "type": TYPE_ENSEIGNANT,
                "description": f"L'enseignant a deja une seance le {_fmt(s)}.",
                "seance_id": s.pk,
            })
    if salle is not None:
        for s in qs.filter(salle=salle):
            conflits.append({
                "type": TYPE_SALLE,
                "description": f"La salle {s.salle.nom_salle} est deja occupee le {_fmt(s)}.",
                "seance_id": s.pk,
            })
    if groupe is not None:
        for s in qs.filter(groupe=groupe):
            conflits.append({
                "type": TYPE_GROUPE,
                "description": f"Le groupe {s.groupe} a deja une seance le {_fmt(s)}.",
                "seance_id": s.pk,
            })
    return conflits
