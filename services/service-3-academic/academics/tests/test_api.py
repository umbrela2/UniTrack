"""Permissions (RG6, UC-ADMIN-03), seances du jour, semaine, non assurees, cron."""
from datetime import date, datetime, timedelta
from io import StringIO

from django.core.management import call_command

from academics.models import Seance

from .base import ADMIN, ETUDIANT, JOUR, PROF_A, PROF_B, BaseCase


class PermissionTests(BaseCase):
    def test_sans_authentification_401(self):
        self.assertEqual(self.client.get("/api/salles/").status_code, 401)

    def test_structure_ecriture_admin_seulement(self):
        body = {"nom_salle": "Amphi 1", "capacite": 200}
        self.assertEqual(self.client.post("/api/salles/", body, **PROF_A).status_code, 403)
        self.assertEqual(self.client.post("/api/salles/", body, **ETUDIANT).status_code, 403)
        self.assertEqual(self.client.post("/api/salles/", body, **ADMIN).status_code, 201)

    def test_structure_lecture_pour_tout_authentifie(self):
        self.assertEqual(self.client.get("/api/groupes/", **PROF_A).status_code, 200)
        self.assertEqual(self.client.get("/api/groupes/", **ETUDIANT).status_code, 200)

    def test_etudiant_ne_touche_pas_aux_seances(self):
        self.assertEqual(self.client.get("/api/seances/", **ETUDIANT).status_code, 403)

    def test_prof_ne_voit_que_ses_seances(self):
        self.make(ens=10)
        self.make(ens=11, groupe=self.g2, salle=self.s2)
        r = self.client.get("/api/seances/", **PROF_A)
        self.assertEqual([s["enseignant_id"] for s in r.data["results"]], [10])
        r = self.client.get("/api/seances/", **ADMIN)
        self.assertEqual(r.data["count"], 2)

    def test_prof_ne_modifie_pas_la_seance_d_un_autre(self):
        autre = self.make(ens=11, groupe=self.g2, salle=self.s2)
        r = self.client.patch(f"/api/seances/{autre.pk}/", {"heure_fin": "09:00"},
                              format="json", **PROF_A)
        self.assertEqual(r.status_code, 404)

    def test_prof_ne_peut_pas_forcer_enseignant_ni_statut(self):
        r = self.client.post("/api/seances/", self.payload(enseignant_id=99, statut="CLOTUREE"),
                             format="json", **PROF_A)
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.data["enseignant_id"], 10)
        self.assertEqual(r.data["statut"], "PLANIFIEE")

    def test_admin_doit_preciser_enseignant(self):
        r = self.client.post("/api/seances/", self.payload(), format="json", **ADMIN)
        self.assertEqual(r.status_code, 400)
        r = self.client.post("/api/seances/", self.payload(enseignant_id=10), format="json", **ADMIN)
        self.assertEqual(r.status_code, 201)

    def test_seance_demarree_non_modifiable_par_prof(self):
        s = self.make(ens=10, statut="EN_COURS")
        r = self.client.patch(f"/api/seances/{s.pk}/", {"heure_fin": "09:00"}, format="json", **PROF_A)
        self.assertEqual(r.status_code, 403)
        self.assertEqual(self.client.delete(f"/api/seances/{s.pk}/", **PROF_A).status_code, 403)

    def test_suppression_seance_planifiee(self):
        s = self.make(ens=10)
        self.assertEqual(self.client.delete(f"/api/seances/{s.pk}/", **PROF_A).status_code, 204)


class TimetableViewsTests(BaseCase):
    def test_today(self):
        self.make(ens=10, jour=date.today())
        self.make(ens=10, jour=date.today() + timedelta(days=1), debut=(8, 0), fin=(9, 0))
        r = self.client.get("/api/seances/today/", **PROF_A)
        self.assertEqual(len(r.data), 1)

    def test_week_grid(self):
        self.make(ens=10, jour=JOUR)  # dimanche 8 nov 2026
        r = self.client.get("/api/timetable/week/", {"date": "2026-11-10"}, **PROF_A)
        self.assertEqual(r.data["semaine_debut"], date(2026, 11, 8))
        self.assertEqual(len(r.data["jours"]), 7)
        self.assertEqual(len(r.data["jours"]["2026-11-08"]), 1)

    def test_week_par_groupe(self):
        self.make(ens=11, groupe=self.g2, salle=self.s2)
        r = self.client.get("/api/timetable/week/", {"date": "2026-11-08", "groupe": self.g2.pk}, **PROF_A)
        self.assertEqual(len(r.data["jours"]["2026-11-08"]), 1)

    def test_non_assurees_admin_seulement(self):
        self.make(statut="NON_ASSUREE")
        self.make(ens=11, groupe=self.g2, salle=self.s2, statut="PLANIFIEE")
        self.assertEqual(self.client.get("/api/seances/non-assurees/", **PROF_A).status_code, 403)
        r = self.client.get("/api/seances/non-assurees/", **ADMIN)
        self.assertEqual(r.data["count"], 1)


class DeclareAbsencesTests(BaseCase):
    def run_cmd(self):
        call_command("declare_absences", stdout=StringIO())

    def test_seance_passee_devient_non_assuree(self):
        passee = self.make(jour=date.today() - timedelta(days=1))
        self.run_cmd()
        passee.refresh_from_db()
        self.assertEqual(passee.statut, "NON_ASSUREE")

    def test_seance_future_inchangee(self):
        future = self.make(jour=date.today() + timedelta(days=1))
        self.run_cmd()
        future.refresh_from_db()
        self.assertEqual(future.statut, "PLANIFIEE")

    def test_seance_demarree_ou_cloturee_inchangee(self):
        hier = date.today() - timedelta(days=1)
        a = self.make(jour=hier, statut="EN_COURS")
        b = self.make(ens=11, jour=hier, groupe=self.g2, salle=self.s2, statut="CLOTUREE")
        self.run_cmd()
        a.refresh_from_db(); b.refresh_from_db()
        self.assertEqual((a.statut, b.statut), ("EN_COURS", "CLOTUREE"))

    def test_seance_du_jour_apres_l_heure_de_fin(self):
        now = datetime.now()
        if now.hour == 0 and now.minute < 2:
            self.skipTest("trop proche de minuit")
        fin = (now - timedelta(minutes=1)).time()
        debut = (now - timedelta(minutes=61)).time()
        s = self.make(jour=now.date(), debut=(debut.hour, debut.minute), fin=(fin.hour, fin.minute))
        self.run_cmd()
        s.refresh_from_db()
        self.assertEqual(s.statut, "NON_ASSUREE")
