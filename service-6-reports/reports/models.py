from django.db import models
from django.utils import timezone


class Groupe(models.Model):
    external_id = models.IntegerField(unique=True)
    numero = models.IntegerField()
    annee_etude = models.IntegerField()
    specialite = models.CharField(max_length=150)

    class Meta:
        ordering = ['specialite', 'numero']

    def __str__(self):
        return f"{self.specialite} - Groupe {self.numero} (Année {self.annee_etude})"


class Module(models.Model):
    external_id = models.IntegerField(unique=True)
    intitule = models.CharField(max_length=200)
    semestre = models.CharField(max_length=10)

    class Meta:
        ordering = ['semestre', 'intitule']

    def __str__(self):
        return f"{self.intitule} ({self.semestre})"


class Salle(models.Model):
    external_id = models.IntegerField(unique=True)
    nom_salle = models.CharField(max_length=100)

    class Meta:
        ordering = ['nom_salle']

    def __str__(self):
        return self.nom_salle


class Enseignant(models.Model):
    external_id = models.IntegerField(unique=True)
    nom = models.CharField(max_length=100)
    prenom = models.CharField(max_length=100)
    email = models.EmailField()

    class Meta:
        ordering = ['nom', 'prenom']

    def __str__(self):
        return f"{self.nom} {self.prenom}"


class Etudiant(models.Model):
    external_id = models.IntegerField(unique=True)
    matricule = models.CharField(max_length=30, unique=True)
    nom = models.CharField(max_length=100)
    prenom = models.CharField(max_length=100)
    email = models.EmailField()
    groupe = models.ForeignKey(
        Groupe,
        on_delete=models.CASCADE,
        related_name='etudiants',
    )

    class Meta:
        ordering = ['nom', 'prenom']

    def __str__(self):
        return f"{self.matricule} - {self.nom} {self.prenom}"


class Seance(models.Model):
    class TypeSeance(models.TextChoices):
        COURS = 'Cours', 'Cours'
        TD = 'TD', 'TD'
        TP = 'TP', 'TP'

    class Statut(models.TextChoices):
        PLANIFIEE = 'Planifiée', 'Planifiée'
        EN_COURS = 'En cours', 'En cours'
        CLOTUREE = 'Clôturée', 'Clôturée'
        NON_ASSURREE = 'Non assurée', 'Non assurée'

    external_id = models.IntegerField(unique=True)
    date_seance = models.DateField()
    heure_debut = models.TimeField()
    heure_fin = models.TimeField()
    type_seance = models.CharField(
        max_length=10,
        choices=TypeSeance.choices,
    )
    statut = models.CharField(
        max_length=20,
        choices=Statut.choices,
    )
    groupe = models.ForeignKey(
        Groupe,
        on_delete=models.CASCADE,
        related_name='seances',
    )
    module = models.ForeignKey(
        Module,
        on_delete=models.CASCADE,
        related_name='seances',
    )
    enseignant = models.ForeignKey(
        Enseignant,
        on_delete=models.CASCADE,
        related_name='seances',
    )
    salle = models.ForeignKey(
        Salle,
        on_delete=models.CASCADE,
        related_name='seances',
    )

    class Meta:
        ordering = ['-date_seance', 'heure_debut']

    def __str__(self):
        return f"{self.module} - {self.groupe} - {self.date_seance}"


class Presence(models.Model):
    class StatutPresence(models.TextChoices):
        PRESENT = 'Présent', 'Présent'
        ABSENT = 'Absent', 'Absent'
        JUSTIFIE = 'Justifié', 'Justifié'

    seance = models.ForeignKey(
        Seance,
        on_delete=models.CASCADE,
        related_name='presences',
    )
    etudiant = models.ForeignKey(
        Etudiant,
        on_delete=models.CASCADE,
        related_name='presences',
    )
    statut_presence = models.CharField(
        max_length=20,
        choices=StatutPresence.choices,
    )
    date_enregistrement = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['seance', 'etudiant'],
                name='unique_presence_seance_etudiant',
            )
        ]

    def __str__(self):
        return f"{self.etudiant} - {self.seance} ({self.statut_presence})"


class ParametresSeuils(models.Model):
    seuil_alerte = models.PositiveIntegerField(default=3)
    seuil_exclusion = models.PositiveIntegerField(default=5)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Paramètres des seuils'
        verbose_name_plural = 'Paramètres des seuils'

    def __str__(self):
        return f"Alerte : {self.seuil_alerte} - Exclusion : {self.seuil_exclusion}"
