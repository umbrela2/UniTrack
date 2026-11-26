from django.contrib import admin

from .models import (
    Enseignant,
    Etudiant,
    Groupe,
    Module,
    ParametresSeuils,
    Presence,
    Salle,
    Seance,
)


@admin.register(Groupe)
class GroupeAdmin(admin.ModelAdmin):
    list_display = ('external_id', 'numero', 'annee_etude', 'specialite')
    list_filter = ('annee_etude', 'specialite')
    search_fields = ('specialite',)


@admin.register(Module)
class ModuleAdmin(admin.ModelAdmin):
    list_display = ('external_id', 'intitule', 'semestre')
    list_filter = ('semestre',)
    search_fields = ('intitule',)


@admin.register(Salle)
class SalleAdmin(admin.ModelAdmin):
    list_display = ('external_id', 'nom_salle')
    search_fields = ('nom_salle',)


@admin.register(Enseignant)
class EnseignantAdmin(admin.ModelAdmin):
    list_display = ('external_id', 'nom', 'prenom', 'email')
    search_fields = ('nom', 'prenom', 'email')


@admin.register(Etudiant)
class EtudiantAdmin(admin.ModelAdmin):
    list_display = ('external_id', 'matricule', 'nom', 'prenom', 'email', 'groupe')
    list_filter = ('groupe',)
    search_fields = ('matricule', 'nom', 'prenom', 'email')
    list_select_related = ('groupe',)


@admin.register(Seance)
class SeanceAdmin(admin.ModelAdmin):
    list_display = (
        'external_id',
        'date_seance',
        'heure_debut',
        'heure_fin',
        'type_seance',
        'statut',
        'groupe',
        'module',
        'enseignant',
        'salle',
    )
    list_filter = (
        'statut',
        'type_seance',
        'date_seance',
        'groupe',
        'module',
        'enseignant',
    )
    search_fields = ('module__intitule', 'groupe__specialite', 'salle__nom_salle')
    list_select_related = ('groupe', 'module', 'enseignant', 'salle')


@admin.register(Presence)
class PresenceAdmin(admin.ModelAdmin):
    list_display = (
        'seance',
        'etudiant',
        'statut_presence',
        'date_enregistrement',
    )
    list_filter = (
        'statut_presence',
        'seance__groupe',
        'seance__module',
    )
    search_fields = ('etudiant__matricule', 'etudiant__nom', 'etudiant__prenom')
    list_select_related = ('seance', 'etudiant')


@admin.register(ParametresSeuils)
class ParametresSeuilsAdmin(admin.ModelAdmin):
    list_display = ('seuil_alerte', 'seuil_exclusion', 'updated_at')
