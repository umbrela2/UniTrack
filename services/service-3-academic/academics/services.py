"""Resolution et creation automatique des donnees academiques.

Le formulaire de seance ne demande plus de choisir des identifiants existants :
il envoie des libelles (departement, annee, specialite, groupe, module,
semestre, salle). Ce module transforme ces libelles en objets Django, en
reutilisant les enregistrements existants et en creant les manquants.

Regles :
- la comparaison est insensible a la casse et aux espaces superflus ;
- les creations sont protegees par une transaction et retentees en cas de
  course concurrente (IntegrityError) ;
- ``create=False`` permet au bouton "Verifier les conflits" de resoudre les
  references existantes SANS rien enregistrer.
"""
import re

from django.db import IntegrityError, transaction
from rest_framework import serializers

from .models import Departement, Groupe, Module, Salle


def clean(value, field, max_length=None):
    """Nettoie un libelle saisi et leve une erreur DRF claire si vide."""
    text = " ".join(str(value if value is not None else "").split())
    if not text:
        raise serializers.ValidationError({field: "Ce champ est obligatoire."})
    if max_length and len(text) > max_length:
        raise serializers.ValidationError(
            {field: f"Maximum {max_length} caracteres."}
        )
    return text


def parse_numero(value):
    """Accepte 1, "1", "G1", "Groupe 1"... et renvoie l'entier."""
    match = re.search(r"\d+", str(value if value is not None else ""))
    if not match:
        raise serializers.ValidationError(
            {"groupe_numero": "Indiquez un numero de groupe (ex. Groupe 1)."}
        )
    numero = int(match.group())
    if numero < 1:
        raise serializers.ValidationError(
            {"groupe_numero": "Le numero de groupe doit etre positif."}
        )
    return numero


def _reuse(model, lookup, defaults):
    """Retourne (objet, cree) en tolerant une creation concurrente."""
    obj = model.objects.filter(**lookup).first()
    if obj is not None:
        return obj, False
    try:
        with transaction.atomic():
            return model.objects.create(**defaults), True
    except IntegrityError:
        obj = model.objects.filter(**lookup).first()
        if obj is not None:
            return obj, False
        raise


def get_departement(nom, *, create=True):
    nom = clean(nom, "departement", 100)
    obj = Departement.objects.filter(nom__iexact=nom).first()
    if obj is not None or not create:
        return obj
    return _reuse(
        Departement, {"nom__iexact": nom}, {"nom": nom}
    )[0]


def get_groupe(departement, annee_etude, specialite, numero, *, create=True):
    annee_etude = clean(annee_etude, "annee_etude", 20)
    specialite = clean(specialite, "specialite", 100)
    numero = parse_numero(numero)

    lookup = {
        "departement": departement,
        "annee_etude__iexact": annee_etude,
        "specialite__iexact": specialite,
        "numero": numero,
    }
    obj = (
        Groupe.objects.select_related("departement")
        .filter(**lookup)
        .first()
    )
    if obj is not None or not create:
        return obj

    return _reuse(
        Groupe,
        lookup,
        {
            "departement": departement,
            "annee_etude": annee_etude,
            "specialite": specialite,
            "numero": numero,
        },
    )[0]


def get_module(departement, intitule, semestre, *, create=True):
    intitule = clean(intitule, "module_intitule", 150)
    semestre = clean(semestre, "semestre", 50)
    lookup = {
        "departement": departement,
        "intitule__iexact": intitule,
        "semestre__iexact": semestre,
    }
    obj = Module.objects.filter(**lookup).first()
    if obj is not None or not create:
        return obj
    return _reuse(
        Module,
        lookup,
        {"departement": departement, "intitule": intitule, "semestre": semestre},
    )[0]


def get_salle(nom, *, create=True):
    nom = clean(nom, "salle_nom", 50)
    obj = Salle.objects.filter(nom_salle__iexact=nom).first()
    if obj is not None or not create:
        return obj
    return _reuse(
        Salle, {"nom_salle__iexact": nom}, {"nom_salle": nom}
    )[0]


def distinct_labels(values):
    """Dedoublonne des libelles sans tenir compte de la casse, en gardant l'ordre."""
    seen, out = set(), []
    for value in values:
        text = str(value or "").strip()
        key = text.casefold()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(text)
    return sorted(out, key=str.casefold)
