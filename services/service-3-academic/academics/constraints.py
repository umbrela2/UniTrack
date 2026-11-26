"""Contraintes PostgreSQL anti-chevauchement (FP3) : derniere ligne de defense.

Pour chaque dimension (enseignant, salle, groupe), deux seances non annulees
ne peuvent pas avoir des intervalles [debut, fin) qui se chevauchent.
Les bornes sont semi-ouvertes : une seance finissant a 10:00 et une autre
commencant a 10:00 ne sont PAS en conflit.
"""
from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import DateTimeRangeField, RangeOperators
from django.db.models import DateTimeField, ExpressionWrapper, F, Func, Q


class TsRange(Func):
    """tsrange(debut, fin) -- '[)' par defaut."""

    function = "tsrange"
    output_field = DateTimeRangeField()


def _creneau():
    debut = ExpressionWrapper(
        F("date_seance") + F("heure_debut"), output_field=DateTimeField()
    )
    fin = ExpressionWrapper(
        F("date_seance") + F("heure_fin"), output_field=DateTimeField()
    )
    return TsRange(debut, fin)


def _exclusion(champ, nom):
    return ExclusionConstraint(
        name=nom,
        expressions=[
            (_creneau(), RangeOperators.OVERLAPS),
            (champ, RangeOperators.EQUAL),
        ],
        condition=~Q(statut="ANNULEE"),
    )


def seance_constraints():
    return [
        _exclusion("enseignant_id", "no_overlap_enseignant"),
        _exclusion("salle", "no_overlap_salle"),
        _exclusion("groupe", "no_overlap_groupe"),
    ]
