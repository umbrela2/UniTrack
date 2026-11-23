"""FP3 / UC-SYS-01 : aucun conflit accepte (enseignant, salle, groupe)."""
from datetime import time

from django.db import IntegrityError, transaction

from academics.models import Seance

from .base import ADMIN, JOUR, PROF_A, PROF_B, BaseCase


def types(resp):
    return {c["type"] for c in resp.data["conflits"]}


class ConflictServiceTests(BaseCase):
    def post(self, headers, **kw):
        return self.client.post("/api/seances/", self.payload(**kw), format="json", **headers)

    def test_creation_sans_conflit(self):
        r = self.post(PROF_A)
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["enseignant_id"], 10)
        self.assertEqual(r.data["statut"], "PLANIFIEE")

    def test_conflit_enseignant(self):
        self.make(ens=10, groupe=self.g1, salle=self.s1)
        r = self.post(PROF_A, groupe=self.g2, salle=self.s2, debut="09:00", fin="10:00")
        self.assertEqual(r.status_code, 409)
        self.assertEqual(types(r), {"ENSEIGNANT"})

    def test_conflit_salle(self):
        self.make(ens=11, groupe=self.g2, salle=self.s1)
        r = self.post(PROF_A, groupe=self.g1, salle=self.s1)
        self.assertEqual(r.status_code, 409)
        self.assertEqual(types(r), {"SALLE"})

    def test_conflit_groupe(self):
        self.make(ens=11, groupe=self.g1, salle=self.s2)
        r = self.post(PROF_A, groupe=self.g1, salle=self.s1)
        self.assertEqual(r.status_code, 409)
        self.assertEqual(types(r), {"GROUPE"})

    def test_meme_infos_qu_un_autre_prof_est_refuse(self):
        self.post(PROF_A)
        r = self.post(PROF_B)  # memes jour, heure, salle, groupe
        self.assertEqual(r.status_code, 409)
        self.assertEqual(types(r), {"SALLE", "GROUPE"})
        self.assertEqual(Seance.objects.count(), 1)

    def test_creneaux_adjacents_acceptes(self):
        self.make(debut=(8, 0), fin=(9, 30))
        r = self.post(PROF_A, debut="09:30", fin="11:00")
        self.assertEqual(r.status_code, 201, r.data)

    def test_chevauchement_partiel_et_inclusion(self):
        self.make(debut=(8, 0), fin=(10, 0))
        for d, f in (("09:00", "11:00"), ("07:00", "08:30"), ("08:30", "09:00"), ("07:00", "11:00")):
            self.assertEqual(self.post(PROF_A, debut=d, fin=f).status_code, 409, (d, f))

    def test_autre_jour_pas_de_conflit(self):
        self.make()
        from datetime import timedelta
        r = self.post(PROF_A, jour=JOUR + timedelta(days=1))
        self.assertEqual(r.status_code, 201)

    def test_seance_annulee_ne_bloque_pas(self):
        self.make(statut="ANNULEE")
        self.assertEqual(self.post(PROF_A).status_code, 201)

    def test_modification_recontrole_les_conflits(self):
        self.make(ens=11, groupe=self.g2, salle=self.s2, debut=(10, 0), fin=(11, 0))
        mine = self.make(ens=10, debut=(8, 0), fin=(9, 0))
        r = self.client.patch(f"/api/seances/{mine.pk}/", {
            "heure_debut": "10:00", "heure_fin": "11:00", "salle": self.s2.pk,
        }, format="json", **PROF_A)
        self.assertEqual(r.status_code, 409)
        self.assertIn("SALLE", types(r))

    def test_modification_sans_conflit_avec_soi_meme(self):
        mine = self.make(ens=10, debut=(8, 0), fin=(9, 0))
        r = self.client.patch(f"/api/seances/{mine.pk}/", {"heure_fin": "09:30"},
                              format="json", **PROF_A)
        self.assertEqual(r.status_code, 200, r.data)

    def test_heure_fin_avant_debut(self):
        r = self.post(PROF_A, debut="10:00", fin="09:00")
        self.assertEqual(r.status_code, 400)

    def test_check_conflicts_dry_run(self):
        self.make(ens=11, groupe=self.g1)
        r = self.client.post("/api/timetable/check-conflicts/", self.payload(),
                             format="json", **PROF_A)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data["conflit"])
        self.assertEqual(Seance.objects.count(), 1)  # rien enregistre


class DatabaseConstraintTests(BaseCase):
    """Derniere ligne de defense : insertion directe qui chevauche => echec."""

    def _insert(self, **kw):
        with transaction.atomic():
            return self.make(**kw)

    def test_bd_refuse_chevauchement_enseignant(self):
        self.make(ens=10, groupe=self.g1, salle=self.s1)
        with self.assertRaises(IntegrityError):
            self._insert(ens=10, groupe=self.g2, salle=self.s2, debut=(9, 0), fin=(10, 0))

    def test_bd_refuse_chevauchement_salle(self):
        self.make(ens=10, groupe=self.g1, salle=self.s1)
        with self.assertRaises(IntegrityError):
            self._insert(ens=11, groupe=self.g2, salle=self.s1)

    def test_bd_refuse_chevauchement_groupe(self):
        self.make(ens=10, groupe=self.g1, salle=self.s1)
        with self.assertRaises(IntegrityError):
            self._insert(ens=11, groupe=self.g1, salle=self.s2)

    def test_bd_accepte_creneaux_adjacents(self):
        self.make(debut=(8, 0), fin=(9, 30))
        self._insert(debut=(9, 30), fin=(11, 0))

    def test_bd_refuse_fin_avant_debut(self):
        with self.assertRaises(IntegrityError):
            self._insert(debut=(10, 0), fin=(9, 0))
