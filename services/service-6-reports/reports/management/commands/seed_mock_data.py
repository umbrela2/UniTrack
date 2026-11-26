import random
import unicodedata
from datetime import datetime, time, timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from reports.models import (
    Enseignant,
    Etudiant,
    Groupe,
    Module,
    ParametresSeuils,
    Presence,
    Salle,
    Seance,
)

GROUPES = [
    (1, 1, 3, 'Génie Logiciel'),
    (2, 2, 3, 'Génie Logiciel'),
    (3, 1, 4, 'Génie Logiciel'),
    (4, 2, 4, 'Génie Logiciel'),
    (5, 1, 3, "Systèmes d'Information"),
]

MODULES = [
    (1, 'Algorithmique avancée', 'S5'),
    (2, 'Bases de données', 'S5'),
    (3, 'Génie logiciel', 'S5'),
    (4, 'Réseaux informatiques', 'S5'),
    (5, 'Programmation web', 'S6'),
    (6, 'Intelligence artificielle', 'S6'),
    (7, "Systèmes d'exploitation", 'S6'),
    (8, 'Sécurité informatique', 'S6'),
]

SALLES = [
    (1, 'Amphi A'),
    (2, 'Amphi B'),
    (3, 'Salle 101'),
    (4, 'Salle 102'),
    (5, 'Laboratoire Informatique 1'),
    (6, 'Laboratoire Informatique 2'),
]

ENSEIGNANTS = [
    (1, 'Benali', 'Karim', 'k.benali@univ-boumerdes.dz'),
    (2, 'Bouzid', 'Amel', 'a.bouzid@univ-boumerdes.dz'),
    (3, 'Cherif', 'Mourad', 'm.cherif@univ-boumerdes.dz'),
    (4, 'Djelloul', 'Samia', 's.djelloul@univ-boumerdes.dz'),
    (5, 'Ferhat', 'Nabil', 'n.ferhat@univ-boumerdes.dz'),
    (6, 'Hamdi', 'Leila', 'l.hamdi@univ-boumerdes.dz'),
    (7, 'Kaci', 'Yacine', 'y.kaci@univ-boumerdes.dz'),
    (8, 'Mansouri', 'Nadia', 'n.mansouri@univ-boumerdes.dz'),
]

PRENOMS = [
    'Amine', 'Yacine', 'Karim', 'Sofiane', 'Mehdi',
    'Riad', 'Bilal', 'Anis', 'Islam', 'Abdelkader',
    'Amel', 'Nadia', 'Lina', 'Yasmine', 'Sara',
    'Meriem', 'Kenza', 'Imane', 'Asma', 'Nour',
    'Ryad', 'Hichem', 'Fouad', 'Samir', 'Zakaria',
    'Rania', 'Hiba', 'Selma', 'Chaima', 'Wissam',
]

NOMS = [
    'Benali', 'Bouzid', 'Cherif', 'Djelloul', 'Ferhat',
    'Hamdi', 'Kaci', 'Mansouri', 'Meziane', 'Boudjelal',
    'Aissani', 'Benkhelifa', 'Taleb', 'Bensalem', 'Khelifi',
    'Saidi', 'Zerrouki', 'Oukil', 'Belaid', 'Rahmani',
]

TIME_SLOTS = [
    (time(8, 0), time(9, 30)),
    (time(9, 45), time(11, 15)),
    (time(11, 30), time(13, 0)),
    (time(13, 30), time(15, 0)),
    (time(15, 15), time(16, 45)),
]

TYPES_SEANCE = [
    Seance.TypeSeance.COURS,
    Seance.TypeSeance.TD,
    Seance.TypeSeance.TP,
]

CLOSED_MODULE_PLAN = {
    0: [2, 2, 2, 2, 2, 2, 1, 3, 5],
    1: [4, 4, 4, 4, 4, 1, 2, 5, 6],
    2: [1, 2, 3, 4, 5, 6, 7, 8, 1],
    3: [2, 3, 4, 5, 6, 7, 8, 1, 2],
    4: [3, 4, 5, 6, 7, 8, 1, 2, 3],
}

OTHER_MODULE_PLAN = {
    0: [6, 7, 8],
    1: [3, 7, 8],
    2: [2, 4, 6],
    3: [4, 5, 7],
    4: [4, 5, 6],
}

OTHER_STATUS_PLAN = {
    0: [Seance.Statut.NON_ASSURREE, Seance.Statut.NON_ASSURREE, Seance.Statut.PLANIFIEE],
    1: [Seance.Statut.NON_ASSURREE, Seance.Statut.NON_ASSURREE, Seance.Statut.PLANIFIEE],
    2: [Seance.Statut.NON_ASSURREE, Seance.Statut.NON_ASSURREE, Seance.Statut.PLANIFIEE],
    3: [Seance.Statut.NON_ASSURREE, Seance.Statut.NON_ASSURREE, Seance.Statut.PLANIFIEE],
    4: [Seance.Statut.PLANIFIEE, Seance.Statut.PLANIFIEE, Seance.Statut.PLANIFIEE],
}


def slugify(value):
    normalized = unicodedata.normalize('NFKD', value)
    return normalized.encode('ascii', 'ignore').decode('ascii').lower()


class Command(BaseCommand):
    help = (
        "Réinitialise et peuple la base avec des données universitaires "
        "réalistes (Université M'hamed Bougara - Boumerdès)."
    )

    @transaction.atomic
    def handle(self, *args, **options):
        self._clear_data()
        self.stdout.write('Anciennes données de test supprimées.')

        groupes = self._create_groupes()
        modules = self._create_modules()
        salles = self._create_salles()
        enseignants = self._create_enseignants()
        etudiants_par_groupe = self._create_etudiants(groupes)
        seances = self._create_seances(
            groupes,
            modules,
            salles,
            enseignants,
        )
        presences = self._create_presences(
            seances,
            etudiants_par_groupe,
            groupes,
            modules,
        )
        ParametresSeuils.objects.create()

        self.stdout.write(self.style.SUCCESS(
            'Données de test générées avec succès : '
            f'{len(groupes)} groupes, {len(modules)} modules, '
            f'{len(salles)} salles, {len(enseignants)} enseignants, '
            f'{sum(len(v) for v in etudiants_par_groupe.values())} étudiants, '
            f'{len(seances)} séances, {len(presences)} présences.'
        ))
        self.stdout.write(
            "Seuils actifs : alerte >= 3 absences, exclusion >= 5 absences. "
            "Des étudiants ciblés dépassent ces seuils en Bases de données "
            "et en Réseaux informatiques."
        )

    def _clear_data(self):
        Presence.objects.all().delete()
        Seance.objects.all().delete()
        Etudiant.objects.all().delete()
        Groupe.objects.all().delete()
        Module.objects.all().delete()
        Salle.objects.all().delete()
        Enseignant.objects.all().delete()
        ParametresSeuils.objects.all().delete()

    def _create_groupes(self):
        return [
            Groupe.objects.create(
                external_id=external_id,
                numero=numero,
                annee_etude=annee_etude,
                specialite=specialite,
            )
            for external_id, numero, annee_etude, specialite in GROUPES
        ]

    def _create_modules(self):
        return [
            Module.objects.create(
                external_id=external_id,
                intitule=intitule,
                semestre=semestre,
            )
            for external_id, intitule, semestre in MODULES
        ]

    def _create_salles(self):
        return [
            Salle.objects.create(
                external_id=external_id,
                nom_salle=nom_salle,
            )
            for external_id, nom_salle in SALLES
        ]

    def _create_enseignants(self):
        return [
            Enseignant.objects.create(
                external_id=external_id,
                nom=nom,
                prenom=prenom,
                email=email,
            )
            for external_id, nom, prenom, email in ENSEIGNANTS
        ]

    def _create_etudiants(self, groupes):
        etudiants_par_groupe = {
            groupe.external_id: [] for groupe in groupes
        }

        for index in range(150):
            groupe = groupes[index // 30]
            prenom = PRENOMS[index % len(PRENOMS)]
            nom = NOMS[(index // len(PRENOMS) + index) % len(NOMS)]
            matricule = f'UMB2023{index + 1:04d}'
            email = (
                f'{slugify(prenom)}.{slugify(nom)}{index + 1}'
                '@etu.univ-boumerdes.dz'
            )

            etudiant = Etudiant.objects.create(
                external_id=index + 1,
                matricule=matricule,
                nom=nom,
                prenom=prenom,
                email=email,
                groupe=groupe,
            )
            etudiants_par_groupe[groupe.external_id].append(etudiant)

        return etudiants_par_groupe

    def _create_seances(self, groupes, modules, salles, enseignants):
        today = timezone.localdate()
        modules_par_external_id = {
            module.external_id: module for module in modules
        }
        seances = []

        for group_index, groupe in enumerate(groupes):
            modules_plan = (
                CLOSED_MODULE_PLAN[group_index]
                + OTHER_MODULE_PLAN[group_index]
            )
            statuses_plan = (
                [Seance.Statut.CLOTUREE] * 9
                + OTHER_STATUS_PLAN[group_index]
            )

            for session_index in range(12):
                date_offset = (session_index * 30) // 12 + group_index % 3
                date_seance = today - timedelta(days=date_offset)
                heure_debut, heure_fin = TIME_SLOTS[
                    (session_index + group_index) % len(TIME_SLOTS)
                ]
                type_seance = TYPES_SEANCE[
                    (session_index + group_index) % len(TYPES_SEANCE)
                ]

                if type_seance == Seance.TypeSeance.TP:
                    salle = salles[4 + (session_index + group_index) % 2]
                else:
                    salle = salles[(session_index + group_index) % 4]

                seance = Seance.objects.create(
                    external_id=len(seances) + 1,
                    date_seance=date_seance,
                    heure_debut=heure_debut,
                    heure_fin=heure_fin,
                    type_seance=type_seance,
                    statut=statuses_plan[session_index],
                    groupe=groupe,
                    module=modules_par_external_id[
                        modules_plan[session_index]
                    ],
                    enseignant=enseignants[
                        (group_index + session_index * 2) % len(enseignants)
                    ],
                    salle=salle,
                )
                seances.append(seance)

        return seances

    def _create_presences(
        self,
        seances,
        etudiants_par_groupe,
        groupes,
        modules,
    ):
        modules_par_external_id = {
            module.external_id: module for module in modules
        }
        premier_groupe = groupes[0]
        deuxieme_groupe = groupes[1]
        etudiants_groupe_1 = etudiants_par_groupe[premier_groupe.external_id]
        etudiants_groupe_2 = etudiants_par_groupe[deuxieme_groupe.external_id]

        seances_bdd = list(
            Seance.objects.filter(
                groupe=premier_groupe,
                module=modules_par_external_id[2],
                statut=Seance.Statut.CLOTUREE,
            ).order_by('date_seance', 'heure_debut')
        )
        seances_reseaux = list(
            Seance.objects.filter(
                groupe=deuxieme_groupe,
                module=modules_par_external_id[4],
                statut=Seance.Statut.CLOTUREE,
            ).order_by('date_seance', 'heure_debut')
        )

        absences_ciblees = {}
        for seance in seances_bdd[:5]:
            absences_ciblees[
                (seance.external_id, etudiants_groupe_1[0].external_id)
            ] = Presence.StatutPresence.ABSENT
        for seance in seances_bdd[:3]:
            absences_ciblees[
                (seance.external_id, etudiants_groupe_1[1].external_id)
            ] = Presence.StatutPresence.ABSENT
        for seance in seances_reseaux[:5]:
            absences_ciblees[
                (seance.external_id, etudiants_groupe_2[0].external_id)
            ] = Presence.StatutPresence.ABSENT
        for seance in seances_reseaux[:3]:
            absences_ciblees[
                (seance.external_id, etudiants_groupe_2[1].external_id)
            ] = Presence.StatutPresence.ABSENT

        rng = random.Random(2026)
        statuts = [
            Presence.StatutPresence.PRESENT,
            Presence.StatutPresence.ABSENT,
            Presence.StatutPresence.JUSTIFIE,
        ]
        presences = []

        for seance in seances:
            if seance.statut != Seance.Statut.CLOTUREE:
                continue

            date_enregistrement = timezone.make_aware(
                datetime.combine(seance.date_seance, seance.heure_fin)
                + timedelta(minutes=10)
            )

            for etudiant in etudiants_par_groupe[seance.groupe.external_id]:
                statut = absences_ciblees.get(
                    (seance.external_id, etudiant.external_id)
                )
                if statut is None:
                    statut = rng.choices(statuts, weights=[80, 15, 5], k=1)[0]

                presences.append(Presence(
                    seance=seance,
                    etudiant=etudiant,
                    statut_presence=statut,
                    date_enregistrement=date_enregistrement,
                ))

        Presence.objects.bulk_create(presences)

        return presences
