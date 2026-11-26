"""Creation manuelle d'une seance + gestion automatique du referentiel.

Le formulaire n'envoie que des libelles : departement, annee, specialite,
groupe, module, semestre, salle. Le backend doit reutiliser l'existant, creer
le manquant, et tout annuler si un conflit est detecte.
"""
from academics.models import Departement, Groupe, Module, Salle, Seance

from .base import ADMIN, JOUR, PROF_A, PROF_B, BaseCase


class SeanceManuelleTests(BaseCase):
    def post(self, headers, **kw):
        return self.client.post(
            "/api/seances/", self.text_payload(**kw), format="json", **headers
        )

    def test_creation_avec_libelles_cree_le_referentiel(self):
        r = self.post(PROF_A, departement="Mathematiques", annee_etude="M1",
                      specialite="MA", groupe_numero="Groupe 2",
                      module_intitule="Analyse", semestre="Semestre impair",
                      salle_nom="Amphi B")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["enseignant_id"], 10)
        self.assertEqual(r.data["departement_nom"], "Mathematiques")
        self.assertEqual(r.data["annee_etude"], "M1")
        self.assertEqual(r.data["specialite"], "MA")
        self.assertEqual(r.data["groupe_numero"], 2)
        self.assertEqual(r.data["semestre"], "Semestre impair")

        groupe = Groupe.objects.get(pk=r.data["groupe"])
        self.assertEqual(groupe.specialite, "MA")
        self.assertEqual(groupe.departement.nom, "Mathematiques")
        self.assertEqual(groupe.annee_etude, "M1")

    def test_reutilisation_insensible_a_la_casse_et_aux_espaces(self):
        avant = (Departement.objects.count(), Groupe.objects.count(),
                 Module.objects.count(), Salle.objects.count())
        r1 = self.post(PROF_A, departement="  informatique ", annee_etude=" l3 ",
                       specialite=" gl ", groupe_numero="G1",
                       module_intitule=" genie   logiciel ", semestre=" s1 ",
                       salle_nom=" salle   1 ")
        self.assertEqual(r1.status_code, 201, r1.data)
        r2 = self.post(PROF_B, debut="10:00", fin="11:00",
                       departement="Informatique", annee_etude="L3",
                       specialite="GL", groupe_numero="1",
                       module_intitule="Genie Logiciel", semestre="S1",
                       salle_nom="Salle 1")
        self.assertEqual(r2.status_code, 201, r2.data)

        self.assertEqual(
            avant,
            (Departement.objects.count(), Groupe.objects.count(),
             Module.objects.count(), Salle.objects.count()),
        )
        self.assertEqual(r1.data["groupe"], self.g1.pk)
        self.assertEqual(r1.data["module"], self.m1.pk)
        self.assertEqual(r1.data["salle"], self.s1.pk)
        self.assertEqual(r2.data["groupe"], self.g1.pk)

    def test_numero_de_groupe_accepte_plusieurs_formats(self):
        for index, numero in enumerate(("Groupe 2", "G2", "2")):
            r = self.post(
                PROF_A, groupe_numero=numero,
                debut=f"{8 + index}:00", fin=f"{9 + index}:00",
                salle_nom=f"Salle {index + 10}",
            )
            self.assertEqual(r.status_code, 201, (numero, r.data))
            self.assertEqual(r.data["groupe_numero"], 2)

    def test_enseignant_identifie_par_le_token(self):
        r = self.post(PROF_A, enseignant_id=99)
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["enseignant_id"], 10)

    def test_admin_doit_fournir_un_enseignant(self):
        r = self.client.post("/api/seances/", self.text_payload(), format="json", **ADMIN)
        self.assertEqual(r.status_code, 400)
        self.assertIn("enseignant_id", r.data)

        r = self.client.post(
            "/api/seances/", self.text_payload(enseignant_id=11),
            format="json", **ADMIN,
        )
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["enseignant_id"], 11)

    def test_champs_academiques_obligatoires(self):
        body = self.text_payload()
        body.pop("departement")
        r = self.client.post("/api/seances/", body, format="json", **PROF_A)
        self.assertEqual(r.status_code, 400)
        self.assertIn("departement", r.data)

        body = self.text_payload()
        body.pop("semestre")
        r = self.client.post("/api/seances/", body, format="json", **PROF_A)
        self.assertEqual(r.status_code, 400)
        self.assertIn("semestre", r.data)

    def test_conflit_annule_aussi_les_donnees_academiques(self):
        self.assertEqual(self.post(PROF_A).status_code, 201)

        avant = (Departement.objects.count(), Groupe.objects.count(),
                 Module.objects.count(), Salle.objects.count(), Seance.objects.count())
        r = self.post(PROF_A, debut="08:30", fin="09:00",
                      departement="Mathematiques", annee_etude="M1",
                      specialite="MA", groupe_numero="Groupe 9",
                      module_intitule="Analyse", semestre="S3",
                      salle_nom="Amphi Z")
        self.assertEqual(r.status_code, 409)
        self.assertIn("ENSEIGNANT", {c["type"] for c in r.data["conflits"]})
        self.assertEqual(
            avant,
            (Departement.objects.count(), Groupe.objects.count(),
             Module.objects.count(), Salle.objects.count(), Seance.objects.count()),
        )
        self.assertFalse(Departement.objects.filter(nom="Mathematiques").exists())
        self.assertFalse(Salle.objects.filter(nom_salle="Amphi Z").exists())

    def test_modification_par_libelles(self):
        r = self.post(PROF_A, departement="Mathematiques", annee_etude="M1",
                      specialite="MA", groupe_numero="Groupe 1",
                      module_intitule="Analyse", semestre="S1",
                      salle_nom="Amphi B")
        self.assertEqual(r.status_code, 201, r.data)
        pk = r.data["id"]

        r = self.client.patch(
            f"/api/seances/{pk}/", {"salle_nom": "Salle 999"},
            format="json", **PROF_A,
        )
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["salle_nom"], "Salle 999")

        r = self.client.patch(
            f"/api/seances/{pk}/", {"annee_etude": "M2"},
            format="json", **PROF_A,
        )
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["annee_etude"], "M2")
        self.assertEqual(r.data["module"], Module.objects.get(intitule="Analyse").pk)

    def test_semestre_libre(self):
        r = self.post(PROF_A, semestre="Semestre impair / option B")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["semestre"], "Semestre impair / option B")


class VerificationConflitsTests(BaseCase):
    def check(self, headers, **kw):
        body = self.text_payload(**kw)
        body.pop("type_seance")
        return self.client.post(
            "/api/timetable/check-conflicts/", body, format="json", **headers
        )

    def test_dry_run_ne_cree_aucune_donnee(self):
        avant = (Departement.objects.count(), Groupe.objects.count(),
                 Module.objects.count(), Salle.objects.count(),
                 Seance.objects.count())
        r = self.check(PROF_A, departement="Mathematiques", annee_etude="M1",
                       specialite="MA", groupe_numero="Groupe 9",
                       module_intitule="Analyse", semestre="S3",
                       salle_nom="Amphi Z")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertFalse(r.data["conflit"])
        self.assertFalse(r.data["salle_existante"])
        self.assertFalse(r.data["groupe_existant"])
        self.assertEqual(
            avant,
            (Departement.objects.count(), Groupe.objects.count(),
             Module.objects.count(), Salle.objects.count(),
             Seance.objects.count()),
        )

    def test_dry_run_detecte_sans_enregistrer(self):
        self.assertEqual(
            self.client.post("/api/seances/", self.text_payload(), format="json", **PROF_A).status_code,
            201,
        )
        r = self.check(PROF_A, debut="08:30", fin="09:00",
                       departement="Mathematiques", annee_etude="M1",
                       specialite="MA", groupe_numero="Groupe 9",
                       module_intitule="Analyse", semestre="S3",
                       salle_nom="Amphi Z")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertTrue(r.data["conflit"])
        self.assertEqual({c["type"] for c in r.data["conflits"]}, {"ENSEIGNANT"})
        self.assertEqual(Seance.objects.count(), 1)
        self.assertFalse(Departement.objects.filter(nom="Mathematiques").exists())

    def test_dry_run_enseignant_ignore_pour_un_prof(self):
        autre = self.make(ens=11, groupe=self.g2, salle=self.s2)
        r = self.check(PROF_A, enseignant_id=11, debut="08:00", fin="09:00")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertFalse(any(c["type"] == "ENSEIGNANT" for c in r.data["conflits"]))
        self.assertEqual(Seance.objects.filter(pk=autre.pk).count(), 1)

    def test_dry_run_admin_exige_enseignant(self):
        r = self.check(ADMIN)
        self.assertEqual(r.status_code, 400)
        self.assertIn("enseignant_id", r.data)

    def test_dry_run_accepte_les_identifiants_historiques(self):
        r = self.client.post(
            "/api/timetable/check-conflicts/", self.payload(),
            format="json", **PROF_A,
        )
        self.assertEqual(r.status_code, 200, r.data)
        self.assertFalse(r.data["conflit"])


class SemaineTests(BaseCase):
    def test_la_semaine_contient_le_contexte_academique(self):
        self.client.post("/api/seances/", self.text_payload(), format="json", **PROF_A)
        r = self.client.get(
            "/api/timetable/week/", {"date": JOUR.isoformat()}, **PROF_A
        )
        self.assertEqual(r.status_code, 200, r.data)
        seance = r.data["jours"][JOUR.isoformat()][0]
        self.assertEqual(seance["departement_nom"], "Informatique")
        self.assertEqual(seance["annee_etude"], "L3")
        self.assertEqual(seance["specialite"], "GL")
        self.assertEqual(seance["groupe_numero"], 1)
        self.assertEqual(seance["semestre"], "S1")
