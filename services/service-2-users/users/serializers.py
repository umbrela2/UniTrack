from django.db import transaction
from rest_framework import serializers
from rest_framework.validators import UniqueValidator

from core.messaging.events import UserEvents
from core.messaging.publisher import publish_user_event

from .models import Role, StudentProfile, TeacherProfile, User


class StudentProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = StudentProfile
        fields = ["matricule", "group_id", "section_id", "date_of_birth", "place_of_birth"]


class TeacherProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = TeacherProfile
        fields = ["grade"]


USER_FIELDS = [
    "id", "email", "first_name", "last_name", "role", "status", "language",
    "phone", "department_id", "student_profile", "teacher_profile",
    "created_at", "updated_at",
]


class UserSerializer(serializers.ModelSerializer):
    student_profile = StudentProfileSerializer(required=False, allow_null=True)
    teacher_profile = TeacherProfileSerializer(required=False, allow_null=True)

    class Meta:
        model = User
        fields = USER_FIELDS
        read_only_fields = ["id", "status", "created_at", "updated_at"]
        extra_kwargs = {
            # all_objects : un email d'un compte supprimé (soft delete) reste réservé
            "email": {
                "validators": [
                    UniqueValidator(
                        queryset=User.all_objects.all(),
                        message="Un utilisateur avec cet email existe déjà.",
                    )
                ]
            }
        }

    def validate(self, attrs):
        # null == "absent" (la réponse d'un GET peut être renvoyée telle quelle en PUT)
        for key in ("student_profile", "teacher_profile"):
            if attrs.get(key) is None:
                attrs.pop(key, None)

        if self.instance is None:
            role = attrs.get("role")
        else:
            role = self.instance.role
            if "role" in attrs and attrs["role"] != role:
                raise serializers.ValidationError({"role": "Le rôle ne peut pas être modifié."})

        has_student = "student_profile" in attrs
        has_teacher = "teacher_profile" in attrs

        if role == Role.STUDENT:
            if self.instance is None and not has_student:
                raise serializers.ValidationError({"student_profile": "Obligatoire pour un étudiant."})
            if has_teacher:
                raise serializers.ValidationError({"teacher_profile": "Interdit pour un étudiant."})
        elif role == Role.TEACHER:
            if has_student:
                raise serializers.ValidationError({"student_profile": "Interdit pour un enseignant."})
        elif has_student or has_teacher:
            raise serializers.ValidationError("Ce rôle n'a pas de profil spécifique.")
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        student_data = validated_data.pop("student_profile", None)
        teacher_data = validated_data.pop("teacher_profile", None)
        user = User.objects.create(**validated_data)
        if student_data is not None:
            StudentProfile.objects.create(user=user, **student_data)
        if teacher_data is not None:
            TeacherProfile.objects.create(user=user, **teacher_data)
        publish_user_event(UserEvents.CREATED, user)
        return user

    @transaction.atomic
    def update(self, instance, validated_data):
        student_data = validated_data.pop("student_profile", None)
        teacher_data = validated_data.pop("teacher_profile", None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()
        if student_data is not None:
            StudentProfile.objects.update_or_create(user=instance, defaults=student_data)
        if teacher_data is not None:
            TeacherProfile.objects.update_or_create(user=instance, defaults=teacher_data)
        fresh = User.objects.select_related("student_profile", "teacher_profile").get(pk=instance.pk)
        publish_user_event(UserEvents.UPDATED, fresh)
        return fresh


class MeSerializer(serializers.ModelSerializer):
    """Mon profil : seuls la langue et le téléphone sont modifiables."""

    student_profile = StudentProfileSerializer(read_only=True)
    teacher_profile = TeacherProfileSerializer(read_only=True)

    class Meta:
        model = User
        fields = USER_FIELDS
        read_only_fields = [
            f for f in USER_FIELDS
            if f not in ("language", "phone", "student_profile", "teacher_profile")
        ]

