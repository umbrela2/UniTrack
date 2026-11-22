import uuid

from django.db import models
from django.utils import timezone


class Role(models.TextChoices):
    STUDENT = "student", "Étudiant"
    TEACHER = "teacher", "Enseignant"
    ADMIN = "admin", "Administrateur"
    SUPERVISOR = "supervisor", "Superviseur"


class Status(models.TextChoices):
    ACTIVE = "active", "Actif"
    DISABLED = "disabled", "Désactivé"


class Language(models.TextChoices):
    FR = "fr", "Français"
    EN = "en", "English"


class AliveManager(models.Manager):
    """Retourne uniquement les enregistrements non supprimés (soft delete)."""

    def get_queryset(self):
        return super().get_queryset().filter(deleted_at__isnull=True)


class User(models.Model):
    """
    Profil d'un utilisateur. Pas de mot de passe ici : les credentials
    sont gérés par S1 (Auth). L'id (UUID) est partagé avec S1 via l'événement user.created.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    role = models.CharField(max_length=20, choices=Role.choices)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.ACTIVE
    )
    language = models.CharField(
        max_length=2, choices=Language.choices, default=Language.FR
    )
    phone = models.CharField(max_length=20, blank=True)
    department_id = models.UUIDField(null=True, blank=True, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True, editable=False)

    objects = AliveManager()
    all_objects = models.Manager()

    class Meta:
        ordering = ["last_name", "first_name"]
        indexes = [
            models.Index(fields=["role"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"{self.last_name} {self.first_name} ({self.role})"

    def save(self, *args, **kwargs):
        self.email = self.email.strip().lower()
        super().save(*args, **kwargs)

    @property
    def is_active(self):
        return self.status == Status.ACTIVE and self.deleted_at is None

    def activate(self):
        self.status = Status.ACTIVE
        self.save(update_fields=["status", "updated_at"])

    def deactivate(self):
        self.status = Status.DISABLED
        self.save(update_fields=["status", "updated_at"])

    def restore(self):
        self.deleted_at = None
        self.status = Status.ACTIVE
        self.save(update_fields=["deleted_at", "status", "updated_at"])

    def soft_delete(self):
        self.deleted_at = timezone.now()
        self.status = Status.DISABLED
        self.save(update_fields=["deleted_at", "status", "updated_at"])


class StudentProfile(models.Model):
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="student_profile"
    )
    matricule = models.CharField(max_length=30, unique=True)
    # UUID simples, PAS de ForeignKey : groupes/sections appartiennent à S3
    group_id = models.UUIDField(null=True, blank=True, db_index=True)
    section_id = models.UUIDField(null=True, blank=True, db_index=True)
    date_of_birth = models.DateField(null=True, blank=True)
    place_of_birth = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return self.matricule


class TeacherProfile(models.Model):
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="teacher_profile"
    )
    grade = models.CharField(max_length=50, blank=True)
   

    def __str__(self):
        return f"{self.user.last_name} - {self.grade}"
