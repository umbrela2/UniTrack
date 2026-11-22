from rest_framework import serializers

from .models import ImportJob

MAX_SIZE = 5 * 1024 * 1024  # 5 Mo


class ImportUploadSerializer(serializers.Serializer):
    file = serializers.FileField()

    def validate_file(self, f):
        if not f.name.lower().endswith((".csv", ".xlsx")):
            raise serializers.ValidationError("Format accepté : .csv ou .xlsx")
        if f.size > MAX_SIZE:
            raise serializers.ValidationError("Fichier trop volumineux (5 Mo maximum).")
        return f


class ImportJobSerializer(serializers.ModelSerializer):
    duration_seconds = serializers.SerializerMethodField()

    class Meta:
        model = ImportJob
        fields = [
            "id", "filename", "status", "total", "success_count",
            "error_count", "errors", "created_at", "finished_at", "duration_seconds",
        ]
        read_only_fields = fields

    def get_duration_seconds(self, obj):
        if obj.finished_at is None:
            return None
        return round((obj.finished_at - obj.created_at).total_seconds(), 2)
