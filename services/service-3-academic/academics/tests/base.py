from datetime import date, time

from rest_framework.test import APITestCase

from academics.models import Departement, Groupe, Module, Salle, Seance

ADMIN = {"HTTP_X_USER_ID": "1", "HTTP_X_USER_ROLE": "admin"}
PROF_A = {"HTTP_X_USER_ID": "10", "HTTP_X_USER_ROLE": "enseignant"}
PROF_B = {"HTTP_X_USER_ID": "11", "HTTP_X_USER_ROLE": "enseignant"}
ETUDIANT = {"HTTP_X_USER_ID": "50", "HTTP_X_USER_ROLE": "etudiant"}

JOUR = date(2026, 11, 8)  # un dimanche


class BaseCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dep = Departement.objects.create(nom="Informatique")
        cls.g1 = Groupe.objects.create(departement=cls.dep, numero=1, annee_etude="L3", specialite="GL")
        cls.g2 = Groupe.objects.create(departement=cls.dep, numero=2, annee_etude="L3", specialite="GL")
        cls.m1 = Module.objects.create(departement=cls.dep, intitule="Genie Logiciel", semestre="S1")
        cls.m2 = Module.objects.create(departement=cls.dep, intitule="Reseaux", semestre="S1")
        cls.s1 = Salle.objects.create(nom_salle="Salle 1")
        cls.s2 = Salle.objects.create(nom_salle="Salle 2")

    def make(self, *, ens=10, groupe=None, salle=None, debut=(8, 0), fin=(9, 30), jour=JOUR,
             statut="PLANIFIEE"):
        return Seance.objects.create(
            date_seance=jour, heure_debut=time(*debut), heure_fin=time(*fin),
            type_seance="TD", statut=statut, module=self.m1,
            groupe=groupe or self.g1, salle=salle or self.s1,
            enseignant_id=ens, created_by=ens,
        )

    def payload(self, *, groupe=None, salle=None, debut="08:00", fin="09:30", jour=JOUR, **extra):
        return {
            "date_seance": jour.isoformat(), "heure_debut": debut, "heure_fin": fin,
            "type_seance": "TD", "module": self.m1.pk,
            "groupe": (groupe or self.g1).pk, "salle": (salle or self.s1).pk, **extra,
        }

    def text_payload(self, *, debut="08:00", fin="09:30", jour=JOUR,
                     departement="Informatique", annee_etude="L3",
                     specialite="GL", groupe_numero="Groupe 1",
                     module_intitule="Genie Logiciel", semestre="S1",
                     salle_nom="Salle 1", **extra):
        """Payload du formulaire : uniquement des libelles academiques."""
        return {
            "date_seance": jour.isoformat(), "heure_debut": debut, "heure_fin": fin,
            "type_seance": "TD", "departement": departement,
            "annee_etude": annee_etude, "specialite": specialite,
            "groupe_numero": groupe_numero, "module_intitule": module_intitule,
            "semestre": semestre, "salle_nom": salle_nom, **extra,
        }
