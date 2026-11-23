from django.db import IntegrityError, transaction
from rest_framework import serializers
from rest_framework.exceptions import APIException

from .conflicts import detect_conflicts
from .models import Departement, Groupe, Module, Salle, Seance
from .notify import send_event
from .services import (
    get_departement, get_groupe, get_module, get_salle,
)


class ConflictError(APIException):
    status_code = 409
    default_code = "conflict"

    def __init__(self, conflicts):
        self.detail = {
            "detail": "Conflit de planification : la seance n'est pas enregistree.",
            "conflits": conflicts,
        }


class DepartementSerializer(serializers.ModelSerializer):
    class Meta:
        model = Departement
        fields = "__all__"


class GroupeSerializer(serializers.ModelSerializer):
    departement_nom = serializers.CharField(
        source="departement.nom", read_only=True
    )

    class Meta:
        model = Groupe
        fields = "__all__"


class ModuleSerializer(serializers.ModelSerializer):
    departement_nom = serializers.CharField(
        source="departement.nom", read_only=True
    )

    class Meta:
        model = Module
        fields = "__all__"


class SalleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Salle
        fields = "__all__"


# ---------------------------------------------------------------------------
# Lecture
# ---------------------------------------------------------------------------
class SeanceReadSerializer(serializers.ModelSerializer):
    """Format de sortie commun a toutes les vues (calendrier, detail, today...)."""

    module_nom = serializers.CharField(source="module.intitule", read_only=True)
    groupe_nom = serializers.CharField(source="groupe.__str__", read_only=True)
    salle_nom = serializers.CharField(source="salle.nom_salle", read_only=True)

    # Contexte academique utile au formulaire d'edition.
    departement_nom = serializers.CharField(
        source="groupe.departement.nom", read_only=True
    )
    annee_etude = serializers.CharField(source="groupe.annee_etude", read_only=True)
    specialite = serializers.CharField(source="groupe.specialite", read_only=True)
    groupe_numero = serializers.IntegerField(source="groupe.numero", read_only=True)
    semestre = serializers.CharField(source="module.semestre", read_only=True)

    class Meta:
        model = Seance
        fields = [
            "id", "date_seance", "heure_debut", "heure_fin", "type_seance",
            "statut", "module", "module_nom", "groupe", "groupe_nom",
            "salle", "salle_nom", "enseignant_id",
            "departement_nom", "annee_etude", "specialite", "groupe_numero",
            "semestre", "created_at", "updated_at",
        ]
        read_only_fields = fields


# ---------------------------------------------------------------------------
# Ecriture : IDs historiques OU libelles academiques (creation automatique)
# ---------------------------------------------------------------------------
class SeanceWriteSerializer(SeanceReadSerializer):
    """Accepte les deux formats d'entree :

    - historique : ``module``, ``groupe``, ``salle`` (identifiants) ;
    - formulaire : ``departement``, ``annee_etude``, ``specialite``,
      ``groupe_numero``, ``module_intitule``, ``semestre``, ``salle_nom``.

    Les libelles sont resolus dans une transaction. Si un conflit est detecte,
    toute la transaction est annulee : aucune donnee academique n'est creee.
    """

    departement = serializers.CharField(required=False, max_length=100)
    annee_etude = serializers.CharField(required=False, max_length=20)
    specialite = serializers.CharField(required=False, max_length=100)
    groupe_numero = serializers.CharField(required=False)
    module_intitule = serializers.CharField(required=False, max_length=150)
    semestre = serializers.CharField(required=False, max_length=50)
    salle_nom = serializers.CharField(required=False, max_length=50)

    class Meta(SeanceReadSerializer.Meta):
        fields = SeanceReadSerializer.Meta.fields + [
            "departement", "module_intitule",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
        extra_kwargs = {
            "module": {"required": False},
            "groupe": {"required": False},
            "salle": {"required": False},
            "enseignant_id": {"required": False},
        }

    # --- champs reserves ---
    def to_internal_value(self, data):
        user = self.context["request"].user
        data = data.copy() if hasattr(data, "copy") else dict(data)
        if not user.is_admin:
            # RG6 : un enseignant ne gere que ses propres seances, au statut PLANIFIEE
            data.pop("statut", None)
            data.pop("enseignant_id", None)
        return super().to_internal_value(data)

    def validate(self, attrs):
        inst = self.instance
        get = lambda k: attrs.get(k, getattr(inst, k) if inst else None)  # noqa: E731
        debut, fin = get("heure_debut"), get("heure_fin")
        if debut and fin and fin <= debut:
            raise serializers.ValidationError(
                {"heure_fin": "L'heure de fin doit etre apres l'heure de debut."}
            )

        user = self.context["request"].user
        if inst is None:
            if user.is_admin:
                if not attrs.get("enseignant_id"):
                    raise serializers.ValidationError(
                        {"enseignant_id": "Obligatoire pour l'administrateur."}
                    )
            else:
                attrs["enseignant_id"] = user.id
        return attrs

    # --- resolution des donnees academiques ---
    @staticmethod
    def _group_input(data):
        return any(
            key in data
            for key in ("departement", "annee_etude", "specialite", "groupe_numero")
        )

    def _resolve_group(self, data, instance):
        if "groupe" in data:
            return data["groupe"]

        if instance is not None and not self._group_input(data):
            return instance.groupe

        current = instance.groupe if instance is not None else None
        departement_nom = data.get("departement") or (
            current.departement.nom if current else None
        )
        annee = data.get("annee_etude") or (current.annee_etude if current else None)
        specialite = data.get("specialite") or (current.specialite if current else None)
        numero = data.get("groupe_numero") or (current.numero if current else None)

        errors = {}
        if not departement_nom:
            errors["departement"] = "Obligatoire pour rattacher la seance."
        if not annee:
            errors["annee_etude"] = "Obligatoire (ex. L3, M1, ING3)."
        if not specialite:
            errors["specialite"] = "Obligatoire (ex. SI, GL, I2A)."
        if not numero:
            errors["groupe_numero"] = "Obligatoire (ex. Groupe 1)."
        if errors:
            raise serializers.ValidationError(errors)

        departement = get_departement(departement_nom)
        return get_groupe(departement, annee, specialite, numero)

    def _resolve_module(self, data, instance, groupe):
        if "module" in data:
            return data["module"]

        module_input = "module_intitule" in data or "semestre" in data
        dept_changed = (
            instance is not None
            and groupe.departement_id != instance.module.departement_id
        )
        if instance is not None and not module_input and not dept_changed:
            return instance.module

        current = instance.module if instance is not None else None
        intitule = data.get("module_intitule") or (current.intitule if current else None)
        semestre = data.get("semestre") or (current.semestre if current else None)

        errors = {}
        if not intitule:
            errors["module_intitule"] = "Obligatoire (ex. Algorithmique)."
        if not semestre:
            errors["semestre"] = "Obligatoire (ex. S1, Semestre 3)."
        if errors:
            raise serializers.ValidationError(errors)

        return get_module(groupe.departement, intitule, semestre)

    def _resolve_salle(self, data, instance):
        if "salle" in data:
            return data["salle"]
        if instance is not None and "salle_nom" not in data:
            return instance.salle

        nom = data.get("salle_nom") or (
            instance.salle.nom_salle if instance is not None else None
        )
        if not nom:
            raise serializers.ValidationError(
                {"salle_nom": "Obligatoire (ex. Salle 101, Amphi A)."}
            )
        return get_salle(nom)

    def _apply_academic_data(self, data, instance):
        """Resout groupe/module/salle puis supprime les libelles de ``data``."""
        groupe = self._resolve_group(data, instance)
        module = self._resolve_module(data, instance, groupe)
        salle = self._resolve_salle(data, instance)

        for key in (
            "departement", "annee_etude", "specialite", "groupe_numero",
            "module_intitule", "semestre", "salle_nom",
        ):
            data.pop(key, None)

        data.update(groupe=groupe, module=module, salle=salle)
        return data

    # --- conflits ---
    def _assert_no_conflicts(self, data, instance=None):
        def value(key):
            if key in data:
                return data[key]
            return getattr(instance, key) if instance is not None else None

        statut = value("statut") or Seance.Statut.PLANIFIEE
        if statut == Seance.Statut.ANNULEE:
            return

        conflits = detect_conflicts(
            date_seance=value("date_seance"),
            heure_debut=value("heure_debut"),
            heure_fin=value("heure_fin"),
            enseignant_id=value("enseignant_id"),
            salle=value("salle"),
            groupe=value("groupe"),
            exclude_id=instance.pk if instance is not None else None,
        )
        if conflits:
            send_event("timetable.conflict", {
                "enseignant_id": value("enseignant_id"), "conflits": conflits,
            })
            raise ConflictError(conflits)

    @staticmethod
    def _db_conflict():
        return ConflictError([{
            "type": "INCONNU",
            "description": "Chevauchement detecte par la base de donnees "
                           "(enseignant, salle ou groupe).",
            "seance_id": None,
        }])

    # --- persistance ---
    def create(self, validated_data):
        user = self.context["request"].user
        with transaction.atomic():
            self._apply_academic_data(validated_data, None)
            validated_data["created_by"] = user.id
            self._assert_no_conflicts(validated_data)
            try:
                with transaction.atomic():
                    return Seance.objects.create(**validated_data)
            except IntegrityError:
                raise self._db_conflict()

    def update(self, instance, validated_data):
        with transaction.atomic():
            self._apply_academic_data(validated_data, instance)
            self._assert_no_conflicts(validated_data, instance)
            for key, value in validated_data.items():
                setattr(instance, key, value)
            try:
                with transaction.atomic():
                    instance.save()
                    return instance
            except IntegrityError:
                raise self._db_conflict()

    def to_representation(self, instance):
        # La reponse d'une creation/modification garde le format de lecture.
        return SeanceReadSerializer(instance, context=self.context).data


# ---------------------------------------------------------------------------
# Verification de conflits (dry-run, aucune ecriture)
# ---------------------------------------------------------------------------
class ConflictCheckSerializer(serializers.Serializer):
    date_seance = serializers.DateField()
    heure_debut = serializers.TimeField()
    heure_fin = serializers.TimeField()

    salle = serializers.PrimaryKeyRelatedField(
        queryset=Salle.objects.all(), required=False
    )
    salle_nom = serializers.CharField(required=False, max_length=50)

    groupe = serializers.PrimaryKeyRelatedField(
        queryset=Groupe.objects.all(), required=False
    )
    departement = serializers.CharField(required=False, max_length=100)
    annee_etude = serializers.CharField(required=False, max_length=20)
    specialite = serializers.CharField(required=False, max_length=100)
    groupe_numero = serializers.CharField(required=False)

    enseignant_id = serializers.IntegerField(required=False)
    exclude_id = serializers.IntegerField(required=False)

    def validate(self, attrs):
        if attrs["heure_fin"] <= attrs["heure_debut"]:
            raise serializers.ValidationError(
                {"heure_fin": "L'heure de fin doit etre apres l'heure de debut."}
            )
        return attrs
