"""Modèles de attendance_db – propriété exclusive du service S4.

Seance / Enrollment sont des *copies locales en lecture* des données publiées par
S3 (Academic Management) : S4 n'accède JAMAIS à la base d'un autre service.
Les identifiants externes (utilisateur, groupe, module, salle) sont des chaînes
opaques fournies par les autres services.
"""
import uuid

from django.db import models
from django.utils import timezone


class SeanceStatus(models.TextChoices):
    PLANIFIEE = "PLANIFIEE", "Planifiée"
    EN_COURS = "EN_COURS", "En cours"
    CLOTUREE = "CLOTUREE", "Clôturée"
    NON_ASSUREE = "NON_ASSUREE", "Non assurée"        # enseignant déclaré absent (FP12)


class SeanceType(models.TextChoices):
    COURS = "COURS", "Cours"
    TD = "TD", "TD"
    TP = "TP", "TP"


class PresenceStatus(models.TextChoices):
    PRESENT = "PRESENT", "Présent"
    ABSENT = "ABSENT", "Absent"


class PresenceMode(models.TextChoices):
    CODE = "CODE", "Saisie du code"
    MANUEL = "MANUEL", "Appel manuel"
    AUTO = "AUTO", "Automatique (clôture)"


class Seance(models.Model):
    academic_seance_id = models.CharField(max_length=64, unique=True)   # id de la séance dans S3
    module_id = models.CharField(max_length=64, db_index=True)
    module_intitule = models.CharField(max_length=200, blank=True)
    semestre = models.CharField(max_length=20, blank=True)
    group_id = models.CharField(max_length=64, db_index=True)
    group_label = models.CharField(max_length=100, blank=True)
    enseignant_id = models.CharField(max_length=64, db_index=True)
    enseignant_nom = models.CharField(max_length=200, blank=True)
    salle_id = models.CharField(max_length=64, blank=True)
    salle_nom = models.CharField(max_length=100, blank=True)
    date_seance = models.DateField(db_index=True)
    heure_debut = models.TimeField()
    heure_fin = models.TimeField()
    type_seance = models.CharField(max_length=10, choices=SeanceType.choices, default=SeanceType.TD)
    statut = models.CharField(max_length=15, choices=SeanceStatus.choices, default=SeanceStatus.PLANIFIEE, db_index=True)
    code_presence = models.CharField(max_length=8, blank=True)
    code_expires_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    declared_absent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["date_seance", "heure_debut"]
        indexes = [
            models.Index(fields=["enseignant_id", "date_seance"]),
            models.Index(fields=["group_id", "date_seance"]),
        ]

    def __str__(self):
        return f"{self.module_intitule or self.module_id} {self.date_seance} {self.heure_debut}"

    def _dt(self, t):
        import datetime as _dt
        return timezone.make_aware(_dt.datetime.combine(self.date_seance, t))

    @property
    def start_dt(self):
        return self._dt(self.heure_debut)

    @property
    def end_dt(self):
        return self._dt(self.heure_fin)


class Enrollment(models.Model):
    """Appartenance étudiant → groupe (réplique alimentée par S2/S3)."""
    student_id = models.CharField(max_length=64, db_index=True)
    group_id = models.CharField(max_length=64, db_index=True)
    matricule = models.CharField(max_length=50, blank=True)
    nom = models.CharField(max_length=100, blank=True)
    prenom = models.CharField(max_length=100, blank=True)
    email = models.EmailField(blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["student_id", "group_id"], name="uniq_student_group")]
        ordering = ["nom", "prenom"]


class Presence(models.Model):
    """Classe d'association Étudiant–Séance (UML) : statut + date d'enregistrement."""
    seance = models.ForeignKey(Seance, on_delete=models.CASCADE, related_name="presences")
    student_id = models.CharField(max_length=64, db_index=True)
    statut = models.CharField(max_length=10, choices=PresenceStatus.choices)
    mode = models.CharField(max_length=10, choices=PresenceMode.choices)
    date_enregistrement = models.DateTimeField(default=timezone.now)
    modifie_par = models.CharField(max_length=64, blank=True)          # trace des corrections manuelles

    class Meta:
        constraints = [models.UniqueConstraint(fields=["seance", "student_id"], name="uniq_presence_per_seance")]  # RG1
        indexes = [models.Index(fields=["student_id", "statut"])]


class AttendanceSettings(models.Model):
    """Paramètres configurables par l'administrateur (singleton, pk=1)."""
    code_validity_minutes = models.PositiveSmallIntegerField(default=5)          # FP5 / RG2
    threshold_warning = models.PositiveSmallIntegerField(default=3)              # FP09 / RG12 : orange
    threshold_critical = models.PositiveSmallIntegerField(default=5)             # FP09 : rouge
    geo_check_enabled = models.BooleanField(default=False)                       # RG15
    geo_latitude = models.FloatField(null=True, blank=True)
    geo_longitude = models.FloatField(null=True, blank=True)
    geo_radius_m = models.PositiveIntegerField(default=300)

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class OutboxEvent(models.Model):
    """Pattern Outbox : l'événement est écrit dans la même transaction que la donnée
    métier, puis publié sur RabbitMQ par le worker (aucune perte si le broker est KO)."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    routing_key = models.CharField(max_length=100)
    payload = models.JSONField()
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    published_at = models.DateTimeField(null=True, blank=True, db_index=True)
    attempts = models.PositiveIntegerField(default=0)
    last_error = models.TextField(blank=True)


class ProcessedMessage(models.Model):
    """Idempotence du consommateur : un message n'est traité qu'une fois."""
    message_id = models.CharField(max_length=100, primary_key=True)
    processed_at = models.DateTimeField(default=timezone.now)
