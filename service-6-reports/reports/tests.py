from datetime import timedelta
from io import BytesIO
import time

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from openpyxl import load_workbook
from rest_framework.test import APITestCase

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

PRESENT = Presence.StatutPresence.PRESENT
ABSENT = Presence.StatutPresence.ABSENT
JUSTIFIE = Presence.StatutPresence.JUSTIFIE


class HealthViewTests(TestCase):
    def test_health_endpoint(self):
        response = self.client.get(reverse('health'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                'service': 'S6: Statistics & Reports',
                'status': 'ok',
                'port': 8006,
            },
        )


class ReportAPITestData(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.groupe_1 = Groupe.objects.create(
            external_id=1,
            numero=1,
            annee_etude=3,
            specialite='Génie Logiciel',
        )
        cls.groupe_2 = Groupe.objects.create(
            external_id=2,
            numero=2,
            annee_etude=3,
            specialite='Génie Logiciel',
        )
        cls.module_1 = Module.objects.create(
            external_id=1,
            intitule='Bases de données',
            semestre='S5',
        )
        cls.module_2 = Module.objects.create(
            external_id=2,
            intitule='Réseaux informatiques',
            semestre='S5',
        )
        cls.salle = Salle.objects.create(
            external_id=1,
            nom_salle='Amphi A',
        )
        cls.enseignant_1 = Enseignant.objects.create(
            external_id=1,
            nom='Benali',
            prenom='Karim',
            email='k.benali@univ-boumerdes.dz',
        )
        cls.enseignant_2 = Enseignant.objects.create(
            external_id=2,
            nom='Bouzid',
            prenom='Amel',
            email='a.bouzid@univ-boumerdes.dz',
        )
        cls.etudiant_a = Etudiant.objects.create(
            external_id=1,
            matricule='ETU001',
            nom='Aissani',
            prenom='Amine',
            email='amine.aissani@etu.univ-boumerdes.dz',
            groupe=cls.groupe_1,
        )
        cls.etudiant_b = Etudiant.objects.create(
            external_id=2,
            matricule='ETU002',
            nom='Belaid',
            prenom='Bilal',
            email='bilal.belaid@etu.univ-boumerdes.dz',
            groupe=cls.groupe_1,
        )
        cls.etudiant_c = Etudiant.objects.create(
            external_id=3,
            matricule='ETU003',
            nom='Cherif',
            prenom='Chaima',
            email='chaima.cherif@etu.univ-boumerdes.dz',
            groupe=cls.groupe_1,
        )
        cls.etudiant_d = Etudiant.objects.create(
            external_id=4,
            matricule='ETU004',
            nom='Djelloul',
            prenom='Dalila',
            email='dalila.djelloul@etu.univ-boumerdes.dz',
            groupe=cls.groupe_2,
        )

        today = timezone.localdate()
        cls.m1_sessions = []
        for index in range(5):
            seance = Seance.objects.create(
                external_id=index + 1,
                date_seance=today - timedelta(days=10 - index),
                heure_debut='08:00',
                heure_fin='09:30',
                type_seance=Seance.TypeSeance.COURS,
                statut=Seance.Statut.CLOTUREE,
                groupe=cls.groupe_1,
                module=cls.module_1,
                enseignant=cls.enseignant_1,
                salle=cls.salle,
            )
            cls.m1_sessions.append(seance)

        cls.m2_sessions = []
        for index in range(3):
            seance = Seance.objects.create(
                external_id=index + 6,
                date_seance=today - timedelta(days=5 - index),
                heure_debut='10:00',
                heure_fin='11:30',
                type_seance=Seance.TypeSeance.TD,
                statut=Seance.Statut.CLOTUREE,
                groupe=cls.groupe_1,
                module=cls.module_2,
                enseignant=cls.enseignant_2,
                salle=cls.salle,
            )
            cls.m2_sessions.append(seance)

        cls.g2_session = Seance.objects.create(
            external_id=9,
            date_seance=today - timedelta(days=4),
            heure_debut='13:30',
            heure_fin='15:00',
            type_seance=Seance.TypeSeance.COURS,
            statut=Seance.Statut.CLOTUREE,
            groupe=cls.groupe_2,
            module=cls.module_1,
            enseignant=cls.enseignant_1,
            salle=cls.salle,
        )
        cls.non_assured_1 = Seance.objects.create(
            external_id=10,
            date_seance=today - timedelta(days=2),
            heure_debut='08:00',
            heure_fin='09:30',
            type_seance=Seance.TypeSeance.TP,
            statut=Seance.Statut.NON_ASSURREE,
            groupe=cls.groupe_1,
            module=cls.module_1,
            enseignant=cls.enseignant_1,
            salle=cls.salle,
        )
        cls.non_assured_2 = Seance.objects.create(
            external_id=11,
            date_seance=today - timedelta(days=1),
            heure_debut='10:00',
            heure_fin='11:30',
            type_seance=Seance.TypeSeance.TD,
            statut=Seance.Statut.NON_ASSURREE,
            groupe=cls.groupe_2,
            module=cls.module_2,
            enseignant=cls.enseignant_1,
            salle=cls.salle,
        )
        Seance.objects.create(
            external_id=12,
            date_seance=today,
            heure_debut='15:15',
            heure_fin='16:45',
            type_seance=Seance.TypeSeance.COURS,
            statut=Seance.Statut.PLANIFIEE,
            groupe=cls.groupe_1,
            module=cls.module_2,
            enseignant=cls.enseignant_2,
            salle=cls.salle,
        )

        for index, seance in enumerate(cls.m1_sessions):
            cls.create_presence(
                seance,
                cls.etudiant_a,
                PRESENT if index < 4 else JUSTIFIE,
            )
            cls.create_presence(seance, cls.etudiant_b, ABSENT)
            cls.create_presence(seance, cls.etudiant_c, PRESENT)

        for index, seance in enumerate(cls.m2_sessions):
            cls.create_presence(
                seance,
                cls.etudiant_a,
                ABSENT if index == 2 else PRESENT,
            )
            cls.create_presence(
                seance,
                cls.etudiant_b,
                ABSENT if index == 2 else PRESENT,
            )
            cls.create_presence(seance, cls.etudiant_c, ABSENT)

        cls.create_presence(cls.g2_session, cls.etudiant_d, PRESENT)

    @classmethod
    def create_presence(cls, seance, etudiant, statut):
        return Presence.objects.create(
            seance=seance,
            etudiant=etudiant,
            statut_presence=statut,
        )


class DashboardSummaryTests(ReportAPITestData):
    def test_dashboard_summary_global_aggregations(self):
        response = self.client.get(reverse('dashboard-summary'))

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(
            data['kpis'],
            {
                'total_seances_cloturees': 9,
                'total_seances_non_assurees': 2,
                'taux_assiduite_global': 60.0,
                'total_absences_non_justifiees': 10,
                'etudiants_en_alerte_count': 2,
                'etudiants_en_exclusion_count': 1,
            },
        )
        self.assertEqual(
            data['presence_breakdown'],
            {
                'presents': 14,
                'absents': 10,
                'justifies': 1,
            },
        )

        by_module = {row['module']: row for row in data['by_module']}

        self.assertEqual(len(by_module), 2)
        self.assertEqual(by_module['Bases de données']['module_id'], 1)
        self.assertEqual(by_module['Bases de données']['nb_seances'], 6)
        self.assertEqual(
            by_module['Bases de données']['taux_assiduite'],
            68.75,
        )
        self.assertEqual(by_module['Bases de données']['total_absences'], 5)
        self.assertEqual(
            by_module['Réseaux informatiques']['nb_seances'],
            3,
        )
        self.assertEqual(
            by_module['Réseaux informatiques']['taux_assiduite'],
            44.44,
        )
        self.assertEqual(
            by_module['Réseaux informatiques']['total_absences'],
            5,
        )

        by_groupe = {row['groupe_id']: row for row in data['by_groupe']}
        self.assertEqual(by_groupe[1]['nb_seances'], 8)
        self.assertEqual(by_groupe[1]['taux_assiduite'], 58.33)
        self.assertEqual(by_groupe[1]['total_absences'], 10)
        self.assertEqual(by_groupe[2]['nb_seances'], 1)
        self.assertEqual(by_groupe[2]['taux_assiduite'], 100.0)
        self.assertEqual(by_groupe[2]['total_absences'], 0)

        self.assertEqual(len(data['students_at_risk']), 2)
        danger, warning = data['students_at_risk']
        self.assertEqual(danger['matricule'], 'ETU002')
        self.assertEqual(danger['module'], 'Bases de données')
        self.assertEqual(danger['absences_non_justifiees'], 5)
        self.assertEqual(danger['niveau_alerte'], 'danger')
        self.assertEqual(warning['matricule'], 'ETU003')
        self.assertEqual(warning['module'], 'Réseaux informatiques')
        self.assertEqual(warning['absences_non_justifiees'], 3)
        self.assertEqual(warning['niveau_alerte'], 'warning')

    def test_dashboard_summary_super_admin_helpers(self):
        response = self.client.get(reverse('dashboard-summary'))

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(
            data['seuils'],
            {'alerte': 3, 'exclusion': 5},
        )
        self.assertEqual(len(data['group_cards']), 3)
        all_card = data['group_cards'][0]
        self.assertIsNone(all_card['groupe_id'])
        self.assertEqual(all_card['groupe'], 'Tous')
        self.assertEqual(all_card['taux_assiduite'], 60.0)
        group_cards = {
            row['groupe_id']: row
            for row in data['group_cards']
            if row['groupe_id'] is not None
        }
        self.assertEqual(group_cards[1]['taux_assiduite'], 58.33)
        self.assertEqual(group_cards[2]['taux_assiduite'], 100.0)

        students = {
            row['matricule']: row
            for row in data['students_detail']
        }
        self.assertEqual(len(students), 4)
        self.assertEqual(students['ETU001']['niveau_alerte'], 'normal')
        self.assertEqual(
            students['ETU002']['niveau_alerte'],
            'danger',
        )
        self.assertEqual(
            students['ETU002']['absences_non_justifiees'],
            5,
        )
        self.assertEqual(
            students['ETU003']['niveau_alerte'],
            'warning',
        )
        self.assertEqual(students['ETU004']['niveau_alerte'], 'normal')

        teachers = {
            (row['enseignant'], row['module']): row
            for row in data['by_enseignant']
        }
        self.assertEqual(len(teachers), 3)
        self.assertEqual(
            teachers[
                ('Benali Karim', 'Bases de données')
            ]['nb_seances_non_assurees'],
            1,
        )
        self.assertEqual(
            teachers[
                ('Benali Karim', 'Bases de données')
            ]['taux_assiduite'],
            68.75,
        )
        self.assertEqual(
            teachers[
                ('Bouzid Amel', 'Réseaux informatiques')
            ]['taux_assiduite'],
            44.44,
        )
        self.assertEqual(
            teachers[
                ('Benali Karim', 'Réseaux informatiques')
            ]['taux_realisation'],
            0.0,
        )

    def test_dashboard_group_cards_ignore_group_filter(self):
        response = self.client.get(
            reverse('dashboard-summary'),
            {'groupe_id': 2},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data['by_groupe']), 1)
        self.assertEqual(len(data['group_cards']), 3)
        group_cards = {
            row['groupe_id']: row
            for row in data['group_cards']
            if row['groupe_id'] is not None
        }
        self.assertEqual(group_cards[1]['taux_assiduite'], 58.33)
        self.assertEqual(group_cards[2]['taux_assiduite'], 100.0)

    def test_dashboard_filters_and_role_scope(self):

        response = self.client.get(
            reverse('dashboard-summary'),
            {'module_id': 1},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['kpis']['total_seances_cloturees'], 6)
        self.assertEqual(data['kpis']['total_seances_non_assurees'], 1)
        self.assertEqual(data['kpis']['total_absences_non_justifiees'], 5)
        self.assertEqual(data['kpis']['etudiants_en_alerte_count'], 1)

        response = self.client.get(
            reverse('dashboard-summary'),
            {'groupe_id': 2},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()['kpis']['total_seances_cloturees'],
            1,
        )

        today = timezone.localdate()
        response = self.client.get(
            reverse('dashboard-summary'),
            {
                'date_from': (today - timedelta(days=7)).isoformat(),
                'date_to': (today - timedelta(days=4)).isoformat(),
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['kpis']['total_seances_cloturees'], 5)
        self.assertEqual(data['kpis']['total_seances_non_assurees'], 0)
        self.assertEqual(data['kpis']['etudiants_en_alerte_count'], 0)

        response = self.client.get(
            reverse('dashboard-summary'),
            {'role': 'enseignant', 'user_id': 2},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['kpis']['total_seances_cloturees'], 3)
        self.assertEqual(data['kpis']['total_seances_non_assurees'], 0)
        self.assertEqual(data['kpis']['taux_assiduite_global'], 44.44)
        self.assertEqual(data['kpis']['etudiants_en_alerte_count'], 1)
        self.assertEqual(data['kpis']['etudiants_en_exclusion_count'], 0)

        response = self.client.get(
            reverse('dashboard-summary'),
            {'role': 'etudiant', 'matricule': 'ETU003'},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['kpis']['total_seances_cloturees'], 8)
        self.assertEqual(data['kpis']['total_seances_non_assurees'], 1)
        self.assertEqual(data['kpis']['etudiants_en_alerte_count'], 2)
        self.assertEqual(data['kpis']['etudiants_en_exclusion_count'], 1)

    def test_dashboard_uses_active_thresholds(self):
        ParametresSeuils.objects.create(
            seuil_alerte=1,
            seuil_exclusion=3,
        )

        response = self.client.get(reverse('dashboard-summary'))

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['kpis']['etudiants_en_alerte_count'], 3)
        self.assertEqual(data['kpis']['etudiants_en_exclusion_count'], 2)
        levels = {
            (row['matricule'], row['module']): row['niveau_alerte']
            for row in data['students_at_risk']
        }
        self.assertEqual(levels[('ETU001', 'Réseaux informatiques')], 'warning')
        self.assertEqual(levels[('ETU002', 'Bases de données')], 'danger')
        self.assertEqual(levels[('ETU003', 'Réseaux informatiques')], 'danger')

    def test_dashboard_rejects_invalid_role(self):
        response = self.client.get(
            reverse('dashboard-summary'),
            {'role': 'inconnu'},
        )
        self.assertEqual(response.status_code, 400)

        response = self.client.get(
            reverse('dashboard-summary'),
            {'role': 'enseignant'},
        )
        self.assertEqual(response.status_code, 400)


class DashboardPageTests(ReportAPITestData):
    def test_dashboard_page_renders_super_admin_layout(self):
        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'reports/dashboard.html')
        self.assertContains(response, 'Supervision Multi-Départements')
        self.assertContains(response, 'Doyen de la Faculté des Sciences')
        self.assertContains(response, '4. Super Admin (Faculté)')
        self.assertContains(response, 'Rapport Officiel PDF (FP12)')
        self.assertContains(response, 'Export Global Excel (FP12)')
        self.assertContains(response, 'Rechercher étudiant / matricule...')
        self.assertContains(response, 'Dr. YAHIATENE')
        self.assertContains(response, 'id="groupCards"')
        self.assertContains(response, 'id="studentBody"')
        self.assertContains(response, 'id="teacherBody"')
        self.assertContains(response, 'id="progressChart"')
        self.assertContains(response, 'id="exportPdf"')
        self.assertContains(response, 'id="exportExcel"')


class NonAssuredSessionsTests(ReportAPITestData):

    def test_non_assured_sessions_list_and_fields(self):
        response = self.client.get(reverse('non-assured-sessions'))

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 2)
        self.assertEqual(data[0]['id'], 11)
        self.assertEqual(data[0]['date_seance'], self.non_assured_2.date_seance.isoformat())
        self.assertEqual(data[0]['heure_debut'], '10:00')
        self.assertEqual(data[0]['heure_fin'], '11:30')
        self.assertEqual(data[0]['type_seance'], 'TD')
        self.assertEqual(data[0]['module'], 'Réseaux informatiques')
        self.assertEqual(data[0]['module_id'], 2)
        self.assertEqual(data[0]['enseignant'], 'Benali Karim')
        self.assertEqual(data[0]['groupe_id'], 2)
        self.assertEqual(data[0]['salle'], 'Amphi A')
        self.assertEqual(data[1]['id'], 10)

    def test_non_assured_sessions_filters(self):
        response = self.client.get(
            reverse('non-assured-sessions'),
            {'module_id': 2},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row['id'] for row in response.json()], [11])

        response = self.client.get(
            reverse('non-assured-sessions'),
            {'groupe_id': 1},
        )
        self.assertEqual([row['id'] for row in response.json()], [10])

        response = self.client.get(
            reverse('non-assured-sessions'),
            {'enseignant_id': 2},
        )
        self.assertEqual(response.json(), [])

        response = self.client.get(
            reverse('non-assured-sessions'),
            {
                'date_from': self.non_assured_2.date_seance.isoformat(),
            },
        )
        self.assertEqual([row['id'] for row in response.json()], [11])


class StudentStatsTests(ReportAPITestData):
    def test_student_stats_overall_and_module_breakdown(self):
        response = self.client.get(
            reverse('student-stats', args=['ETU003']),
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['etudiant']['matricule'], 'ETU003')
        self.assertEqual(data['etudiant']['nom'], 'Cherif')
        self.assertEqual(data['etudiant']['prenom'], 'Chaima')
        self.assertEqual(data['etudiant']['groupe_id'], 1)
        self.assertEqual(data['taux_assiduite_global'], 62.5)
        self.assertEqual(data['total_absences_non_justifiees'], 3)

        by_module = {row['module']: row for row in data['by_module']}
        self.assertEqual(by_module['Bases de données']['total_seances'], 5)
        self.assertEqual(by_module['Bases de données']['presents'], 5)
        self.assertEqual(
            by_module['Bases de données']['absents_non_justifies'],
            0,
        )
        self.assertEqual(by_module['Bases de données']['justifies'], 0)
        self.assertEqual(
            by_module['Bases de données']['taux_assiduite'],
            100.0,
        )
        self.assertEqual(
            by_module['Bases de données']['statut_alerte'],
            'ok',
        )
        self.assertEqual(
            by_module['Réseaux informatiques']['total_seances'],
            3,
        )
        self.assertEqual(
            by_module['Réseaux informatiques']['absents_non_justifies'],
            3,
        )
        self.assertEqual(
            by_module['Réseaux informatiques']['taux_assiduite'],
            0.0,
        )
        self.assertEqual(
            by_module['Réseaux informatiques']['statut_alerte'],
            'warning',
        )

    def test_student_stats_danger_threshold(self):
        response = self.client.get(
            reverse('student-stats', args=['ETU002']),
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['taux_assiduite_global'], 25.0)
        self.assertEqual(data['total_absences_non_justifiees'], 6)

        by_module = {row['module']: row for row in data['by_module']}
        self.assertEqual(
            by_module['Bases de données']['absents_non_justifies'],
            5,
        )
        self.assertEqual(
            by_module['Bases de données']['statut_alerte'],
            'danger',
        )
        self.assertEqual(
            by_module['Réseaux informatiques']['absents_non_justifies'],
            1,
        )
        self.assertEqual(
            by_module['Réseaux informatiques']['statut_alerte'],
            'ok',
        )

    def test_student_stats_unknown_returns_404(self):
        response = self.client.get(
            reverse('student-stats', args=['INCONNU']),
        )
        self.assertEqual(response.status_code, 404)


class SyncEndpointTests(ReportAPITestData):
    def sync_payload(self, base):
        groupe_id = base + 1
        module_id = base + 2
        salle_id = base + 3
        enseignant_id = base + 4
        etudiant_id = base + 5
        seance_id = base + 6
        return {
            'groupes': [{
                'external_id': groupe_id,
                'numero': 9,
                'annee_etude': 2,
                'specialite': 'Informatique',
            }],
            'modules': [{
                'external_id': module_id,
                'intitule': 'Architecture logicielle',
                'semestre': 'S4',
            }],
            'salles': [{
                'external_id': salle_id,
                'nom_salle': 'Salle 201',
            }],
            'enseignants': [{
                'external_id': enseignant_id,
                'nom': 'Meziane',
                'prenom': 'Sofiane',
                'email': 's.meziane@univ-boumerdes.dz',
            }],
            'etudiants': [{
                'external_id': etudiant_id,
                'matricule': f'SYNC{base}',
                'nom': 'Kaci',
                'prenom': 'Nour',
                'email': f'nour.kaci{base}@etu.univ-boumerdes.dz',
                'groupe_id': groupe_id,
            }],
            'seances': [{
                'external_id': seance_id,
                'date_seance': '2026-11-01',
                'heure_debut': '08:00',
                'heure_fin': '09:30',
                'type_seance': 'Cours',
                'statut': 'Clôturée',
                'groupe_id': groupe_id,
                'module_id': module_id,
                'enseignant_id': enseignant_id,
                'salle_id': salle_id,
            }],
            'presences': [{
                'seance_id': seance_id,
                'etudiant_id': etudiant_id,
                'statut_presence': 'Présent',
                'date_enregistrement': '2026-11-01T09:40:00+01:00',
            }],
        }

    def test_sync_creates_all_entities(self):
        response = self.client.post(
            reverse('sync'),
            self.sync_payload(100),
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'ok')
        self.assertEqual(data['total_processed'], 7)
        for bucket in (
            'groupes',
            'modules',
            'salles',
            'enseignants',
            'etudiants',
            'seances',
            'presences',
        ):
            self.assertEqual(data['created'][bucket], 1)
            self.assertEqual(data['updated'][bucket], 0)

        groupe = Groupe.objects.get(external_id=101)
        etudiant = Etudiant.objects.get(external_id=105)
        seance = Seance.objects.get(external_id=106)
        presence = Presence.objects.get(etudiant=etudiant, seance=seance)

        self.assertEqual(groupe.specialite, 'Informatique')
        self.assertEqual(etudiant.groupe, groupe)
        self.assertEqual(seance.module.external_id, 102)
        self.assertEqual(seance.enseignant.external_id, 104)
        self.assertEqual(seance.salle.external_id, 103)
        self.assertEqual(presence.statut_presence, 'Présent')

    def test_sync_updates_existing_entities_idempotently(self):
        payload = self.sync_payload(200)
        first = self.client.post(reverse('sync'), payload, format='json')
        self.assertEqual(first.status_code, 200)

        payload['groupes'][0]['specialite'] = 'Informatique appliquée'
        payload['modules'][0]['intitule'] = 'Architecture avancée'
        payload['seances'][0]['statut'] = 'Non assurée'
        payload['presences'][0]['statut_presence'] = 'Absent'

        response = self.client.post(reverse('sync'), payload, format='json')

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['total_processed'], 7)
        for bucket in data['created']:
            self.assertEqual(data['created'][bucket], 0)
            self.assertEqual(data['updated'][bucket], 1)

        self.assertEqual(
            Groupe.objects.get(external_id=201).specialite,
            'Informatique appliquée',
        )
        self.assertEqual(
            Module.objects.get(external_id=202).intitule,
            'Architecture avancée',
        )
        self.assertEqual(
            Seance.objects.get(external_id=206).statut,
            'Non assurée',
        )
        self.assertEqual(
            Presence.objects.get(
                seance__external_id=206,
                etudiant__external_id=205,
            ).statut_presence,
            'Absent',
        )

    def test_sync_accepts_event_style_payload(self):
        response = self.client.post(
            reverse('sync'),
            {
                'event': 'groupe.updated',
                'data': {
                    'external_id': 1,
                    'specialite': 'Génie Logiciel et Systèmes',
                },
            },
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['updated']['groupes'], 1)
        self.assertEqual(
            Groupe.objects.get(external_id=1).specialite,
            'Génie Logiciel et Systèmes',
        )

    def test_sync_rolls_back_on_invalid_reference(self):
        payload = {
            'groupes': [{
                'external_id': 501,
                'numero': 1,
                'annee_etude': 1,
                'specialite': 'Test',
            }],
            'etudiants': [{
                'external_id': 502,
                'matricule': 'ROLLBACK',
                'nom': 'Test',
                'prenom': 'Rollback',
                'email': 'rollback@etu.univ-boumerdes.dz',
                'groupe_id': 999,
            }],
        }

        response = self.client.post(reverse('sync'), payload, format='json')

        self.assertEqual(response.status_code, 400)
        self.assertFalse(Groupe.objects.filter(external_id=501).exists())
        self.assertFalse(Etudiant.objects.filter(external_id=502).exists())

    def test_sync_rejects_payload_without_entities(self):
        response = self.client.post(
            reverse('sync'),
            {'source': 'S3'},
            format='json',
        )
        self.assertEqual(response.status_code, 400)


class ExportEndpointTests(ReportAPITestData):
    def test_excel_export_returns_valid_workbook_quickly(self):
        started = time.perf_counter()
        response = self.client.get(reverse('export-excel'))
        elapsed = time.perf_counter() - started

        self.assertLess(elapsed, 5)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response['Content-Type'],
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        self.assertEqual(
            response['Content-Disposition'],
            'attachment; filename="unitrack_report.xlsx"',
        )
        self.assertTrue(response.content.startswith(b'PK'))
        self.assertGreater(len(response.content), 0)

        workbook = load_workbook(BytesIO(response.content))
        sheet = workbook.active
        self.assertEqual(
            sheet['A1'].value,
            "UniTrack - Université M'hamed Bougara Boumerdès",
        )
        headers = [
            sheet.cell(row=6, column=index).value
            for index in range(1, 5)
        ]
        self.assertEqual(headers, [
            'Module',
            'Séances clôturées',
            'Absences non justifiées',
            "Taux d'assiduité (%)",
        ])
        self.assertEqual(sheet.cell(row=7, column=1).value, 'Bases de données')
        self.assertEqual(sheet.cell(row=9, column=1).value, 'TOTAL')

    def test_pdf_export_returns_valid_pdf_quickly(self):
        started = time.perf_counter()
        response = self.client.get(reverse('export-pdf'))
        elapsed = time.perf_counter() - started

        self.assertLess(elapsed, 5)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertEqual(
            response['Content-Disposition'],
            'attachment; filename="unitrack_report.pdf"',
        )
        self.assertTrue(response.content.startswith(b'%PDF'))
        self.assertGreater(len(response.content), 0)

    def test_exports_support_all_report_types(self):
        for report_type in (
            'attendance_summary',
            'students_at_risk',
            'non_assured_sessions',
        ):
            for url_name, prefix in (
                ('export-excel', b'PK'),
                ('export-pdf', b'%PDF'),
            ):
                with self.subTest(report_type=report_type, url=url_name):
                    started = time.perf_counter()
                    response = self.client.get(
                        reverse(url_name),
                        {'report_type': report_type, 'module_id': 1},
                    )
                    elapsed = time.perf_counter() - started

                    self.assertLess(elapsed, 5)
                    self.assertEqual(response.status_code, 200)
                    self.assertTrue(response.content.startswith(prefix))
                    self.assertGreater(len(response.content), 0)

    def test_exports_reject_invalid_report_type(self):
        for url_name in ('export-excel', 'export-pdf'):
            with self.subTest(url=url_name):
                response = self.client.get(
                    reverse(url_name),
                    {'report_type': 'inconnu'},
                )
                self.assertEqual(response.status_code, 400)
