from django.db import models
from django.db.models import F, Q

from .constraints import seance_constraints


class Departement(models.Model):
    nom = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.nom


class Groupe(models.Model):
    departement = models.ForeignKey(
        Departement, on_delete=models.PROTECT, related_name="groupes"
    )
    numero = models.PositiveIntegerField()
    # Libelle libre : L1, L2, L3, M1, M2, ING3...
    annee_etude = models.CharField(max_length=20)
    specialite = models.CharField(max_length=100)

    class Meta:
        unique_together = ("departement", "annee_etude", "specialite", "numero")
        ordering = ["annee_etude", "specialite", "numero"]

    def __str__(self):
        return f"{self.specialite} - G{self.numero} ({self.annee_etude})"


class Module(models.Model):
    departement = models.ForeignKey(
        Departement, on_delete=models.PROTECT, related_name="modules"
    )
    intitule = models.CharField(max_length=150)
    semestre = models.CharField(max_length=50)  # saisie libre : S1, Semestre 3...

    class Meta:
        unique_together = ("departement", "intitule", "semestre")

    def __str__(self):
        return f"{self.intitule} ({self.semestre})"


class Salle(models.Model):
    nom_salle = models.CharField(max_length=50, unique=True)
    capacite = models.PositiveIntegerField(null=True, blank=True)

    def __str__(self):
        return self.nom_salle


class Seance(models.Model):
    class Type(models.TextChoices):
        COURS = "COURS", "Cours"
        TD = "TD", "TD"
        TP = "TP", "TP"

    class Statut(models.TextChoices):  # Annexe C
        PLANIFIEE = "PLANIFIEE", "Planifiée"
        EN_COURS = "EN_COURS", "En cours"
        CLOTUREE = "CLOTUREE", "Clôturée"
        ANNULEE = "ANNULEE", "Annulée"
        NON_ASSUREE = "NON_ASSUREE", "Non assurée"

    date_seance = models.DateField()
    heure_debut = models.TimeField()
    heure_fin = models.TimeField()
    type_seance = models.CharField(max_length=10, choices=Type.choices)
    statut = models.CharField(
        max_length=15, choices=Statut.choices, default=Statut.PLANIFIEE
    )

    module = models.ForeignKey(Module, on_delete=models.PROTECT, related_name="seances")
    groupe = models.ForeignKey(Groupe, on_delete=models.PROTECT, related_name="seances")
    salle = models.ForeignKey(Salle, on_delete=models.PROTECT, related_name="seances")
    # id de l'enseignant dans le Service 2 : pas de FK inter-services
    enseignant_id = models.PositiveIntegerField(db_index=True)

    created_by = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["date_seance", "heure_debut"]
        indexes = [
            models.Index(fields=["enseignant_id", "date_seance"]),
            models.Index(fields=["groupe", "date_seance"]),
            models.Index(fields=["statut", "date_seance"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(heure_fin__gt=F("heure_debut")),
                name="seance_fin_apres_debut",
            ),
            *seance_constraints(),
        ]

    def __str__(self):
        return f"{self.module} - {self.date_seance} {self.heure_debut}-{self.heure_fin}"
