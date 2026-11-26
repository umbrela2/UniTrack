from django.utils import timezone
from rest_framework import serializers

from .models import AttendanceSettings, Presence, PresenceStatus, Seance, SeanceStatus


class SeanceSerializer(serializers.ModelSerializer):
    """Le code de présence n'est JAMAIS exposé ici (il est servi uniquement à l'enseignant propriétaire)."""
    statut_label = serializers.CharField(source="get_statut_display", read_only=True)
    code_active = serializers.SerializerMethodField()

    class Meta:
        model = Seance
        fields = ["id", "academic_seance_id", "module_id", "module_intitule", "semestre", "group_id", "group_label",
                  "enseignant_id", "enseignant_nom", "salle_nom", "date_seance", "heure_debut", "heure_fin",
                  "type_seance", "statut", "statut_label", "code_active", "started_at", "closed_at",
                  "declared_absent_at"]
        read_only_fields = fields

    def get_code_active(self, obj):
        return bool(obj.statut == SeanceStatus.EN_COURS and obj.code_expires_at and obj.code_expires_at > timezone.now())


class CheckInSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=8)
    latitude = serializers.FloatField(required=False, min_value=-90, max_value=90)
    longitude = serializers.FloatField(required=False, min_value=-180, max_value=180)


class ManualPresenceSerializer(serializers.Serializer):
    statut = serializers.ChoiceField(choices=PresenceStatus.choices)


class SettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = AttendanceSettings
        exclude = ["id"]

    def validate(self, attrs):
        warn = attrs.get("threshold_warning", getattr(self.instance, "threshold_warning", 3))
        crit = attrs.get("threshold_critical", getattr(self.instance, "threshold_critical", 5))
        if warn >= crit:
            raise serializers.ValidationError("threshold_warning doit être inférieur à threshold_critical.")
        if attrs.get("geo_check_enabled") and (attrs.get("geo_latitude") is None and
                                               getattr(self.instance, "geo_latitude", None) is None):
            raise serializers.ValidationError("Latitude/longitude requises pour activer la vérification de position.")
        return attrs


class PresenceRecordSerializer(serializers.ModelSerializer):
    date_seance = serializers.DateField(source="seance.date_seance")
    heure_debut = serializers.TimeField(source="seance.heure_debut")
    module_id = serializers.CharField(source="seance.module_id")
    module_intitule = serializers.CharField(source="seance.module_intitule")
    group_id = serializers.CharField(source="seance.group_id")
    enseignant_id = serializers.CharField(source="seance.enseignant_id")
    enseignant_nom = serializers.CharField(source="seance.enseignant_nom")
    seance_id = serializers.IntegerField(source="seance.id")

    class Meta:
        model = Presence
        fields = ["id", "seance_id", "student_id", "statut", "mode", "date_enregistrement", "date_seance",
                  "heure_debut", "module_id", "module_intitule", "group_id", "enseignant_id", "enseignant_nom"]
