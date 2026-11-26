from django.db.models import Count, F, Q
from django.utils.dateparse import parse_date
from rest_framework.exceptions import NotFound, ValidationError

from .models import Enseignant, Etudiant, ParametresSeuils, Presence, Seance

DEFAULT_SEUIL_ALERTE = 3
DEFAULT_SEUIL_EXCLUSION = 5

PRESENT = Presence.StatutPresence.PRESENT
ABSENT = Presence.StatutPresence.ABSENT
JUSTIFIE = Presence.StatutPresence.JUSTIFIE


def get_active_thresholds():
    parametres = ParametresSeuils.objects.order_by('-updated_at', '-id').first()
    if parametres is None:
        return DEFAULT_SEUIL_ALERTE, DEFAULT_SEUIL_EXCLUSION

    return parametres.seuil_alerte, parametres.seuil_exclusion


def parse_int_param(params, name):
    value = params.get(name)
    if value in (None, ''):
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValidationError({name: 'Ce filtre doit être un entier.'})


def parse_date_param(params, name):
    value = params.get(name)
    if value in (None, ''):
        return None

    parsed = parse_date(value)
    if parsed is None:
        raise ValidationError({name: 'Format de date attendu : YYYY-MM-DD.'})

    return parsed


def filter_sessions(queryset, params):
    module_id = parse_int_param(params, 'module_id')
    groupe_id = parse_int_param(params, 'groupe_id')
    enseignant_id = parse_int_param(params, 'enseignant_id')
    date_from = parse_date_param(params, 'date_from')
    date_to = parse_date_param(params, 'date_to')

    if module_id is not None:
        queryset = queryset.filter(module__external_id=module_id)
    if groupe_id is not None:
        queryset = queryset.filter(groupe__external_id=groupe_id)
    if enseignant_id is not None:
        queryset = queryset.filter(enseignant__external_id=enseignant_id)
    if date_from is not None:
        queryset = queryset.filter(date_seance__gte=date_from)
    if date_to is not None:
        queryset = queryset.filter(date_seance__lte=date_to)

    return queryset


def apply_role_filter(queryset, params):
    role = (params.get('role') or 'admin').strip().lower()

    if role in ('admin', 'superviseur'):
        return queryset

    if role == 'enseignant':
        user_id = parse_int_param(params, 'user_id')
        if user_id is None:
            raise ValidationError({
                'user_id': 'Ce paramètre est requis pour le rôle enseignant.',
            })
        if not Enseignant.objects.filter(external_id=user_id).exists():
            raise NotFound('Enseignant introuvable.')

        return queryset.filter(enseignant__external_id=user_id)

    if role == 'etudiant':
        matricule = (params.get('matricule') or '').strip()
        if not matricule:
            raise ValidationError({
                'matricule': 'Ce paramètre est requis pour le rôle étudiant.',
            })

        etudiant = (
            Etudiant.objects.select_related('groupe')
            .filter(matricule=matricule)
            .first()
        )
        if etudiant is None:
            raise NotFound('Étudiant introuvable.')

        return queryset.filter(groupe=etudiant.groupe)

    raise ValidationError({
        'role': (
            'Rôle invalide. Valeurs acceptées : admin, superviseur, '
            'enseignant, etudiant.'
        ),
    })


def attendance_rate(attended, total):
    if not total:
        return 0.0
    return round((attended / total) * 100, 2)


def build_attendance_totals(presence_queryset):
    totals = presence_queryset.aggregate(
        total=Count('id'),
        presents=Count('id', filter=Q(statut_presence=PRESENT)),
        justifies=Count('id', filter=Q(statut_presence=JUSTIFIE)),
        absents=Count('id', filter=Q(statut_presence=ABSENT)),
    )
    totals['attended'] = totals['presents'] + totals['justifies']
    totals['taux_assiduite'] = attendance_rate(
        totals['attended'],
        totals['total'],
    )
    return totals


def build_by_module(closed_sessions, presence_queryset):
    module_sessions = (
        closed_sessions.values(
            'module__external_id',
            'module__intitule',
        )
        .annotate(nb_seances=Count('id'))
    )
    module_presences = (
        presence_queryset.values(
            'seance__module__external_id',
            'seance__module__intitule',
        )
        .annotate(
            total_presences=Count('id'),
            presents=Count(
                'id',
                filter=Q(statut_presence=PRESENT),
            ),
            justifies=Count(
                'id',
                filter=Q(statut_presence=JUSTIFIE),
            ),
            absents=Count(
                'id',
                filter=Q(statut_presence=ABSENT),
            ),
        )
        .annotate(attended=F('presents') + F('justifies'))
    )
    module_presence_map = {
        row['seance__module__external_id']: row
        for row in module_presences
    }

    by_module = []
    for row in sorted(
        module_sessions,
        key=lambda item: item['module__intitule'],
    ):
        module_id = row['module__external_id']
        presence_row = module_presence_map.get(module_id)
        total_presences = (
            presence_row['total_presences'] if presence_row else 0
        )
        module_attended = presence_row['attended'] if presence_row else 0

        by_module.append({
            'module_id': module_id,
            'module': row['module__intitule'],
            'taux_assiduite': attendance_rate(
                module_attended,
                total_presences,
            ),
            'total_absences': (
                presence_row['absents'] if presence_row else 0
            ),
            'nb_seances': row['nb_seances'],
        })

    return by_module


def build_by_groupe(closed_sessions, presence_queryset):
    group_sessions = (
        closed_sessions.values(
            'groupe__external_id',
            'groupe__numero',
            'groupe__annee_etude',
            'groupe__specialite',
        )
        .annotate(nb_seances=Count('id'))
    )
    group_presences = (
        presence_queryset.values('seance__groupe__external_id')
        .annotate(
            total_presences=Count('id'),
            presents=Count(
                'id',
                filter=Q(statut_presence=PRESENT),
            ),
            justifies=Count(
                'id',
                filter=Q(statut_presence=JUSTIFIE),
            ),
            absents=Count(
                'id',
                filter=Q(statut_presence=ABSENT),
            ),
        )
        .annotate(attended=F('presents') + F('justifies'))
    )
    group_presence_map = {
        row['seance__groupe__external_id']: row
        for row in group_presences
    }

    by_groupe = []
    for row in sorted(
        group_sessions,
        key=lambda item: (
            item['groupe__specialite'],
            item['groupe__numero'],
        ),
    ):
        groupe_id = row['groupe__external_id']
        presence_row = group_presence_map.get(groupe_id)
        total_presences = (
            presence_row['total_presences'] if presence_row else 0
        )
        group_attended = presence_row['attended'] if presence_row else 0

        by_groupe.append({
            'groupe_id': groupe_id,
            'groupe': (
                f"{row['groupe__specialite']} - Groupe "
                f"{row['groupe__numero']} "
                f"(Année {row['groupe__annee_etude']})"
            ),
            'taux_assiduite': attendance_rate(
                group_attended,
                total_presences,
            ),
            'total_absences': (
                presence_row['absents'] if presence_row else 0
            ),
            'nb_seances': row['nb_seances'],
        })

    return by_groupe


def build_by_enseignant(sessions, presence_queryset):
    session_rows = (
        sessions.values(
            'enseignant__external_id',
            'enseignant__nom',
            'enseignant__prenom',
            'module__external_id',
            'module__intitule',
        )
        .annotate(
            total_seances=Count('id'),
            nb_seances_cloturees=Count(
                'id',
                filter=Q(statut=Seance.Statut.CLOTUREE),
            ),
            nb_seances_non_assurees=Count(
                'id',
                filter=Q(statut=Seance.Statut.NON_ASSURREE),
            ),
        )
    )
    presence_rows = (
        presence_queryset.values(
            'seance__enseignant__external_id',
            'seance__module__external_id',
        )
        .annotate(
            total_presences=Count('id'),
            presents=Count(
                'id',
                filter=Q(statut_presence=PRESENT),
            ),
            justifies=Count(
                'id',
                filter=Q(statut_presence=JUSTIFIE),
            ),
        )
        .annotate(attended=F('presents') + F('justifies'))
    )
    presence_map = {
        (
            row['seance__enseignant__external_id'],
            row['seance__module__external_id'],
        ): row
        for row in presence_rows
    }

    by_enseignant = []
    for row in sorted(
        session_rows,
        key=lambda item: (
            -item['nb_seances_non_assurees'],
            item['enseignant__nom'],
            item['enseignant__prenom'],
            item['module__intitule'],
        ),
    ):
        key = (
            row['enseignant__external_id'],
            row['module__external_id'],
        )
        presence_row = presence_map.get(key)
        total_presences = (
            presence_row['total_presences'] if presence_row else 0
        )
        attended = presence_row['attended'] if presence_row else 0

        by_enseignant.append({
            'enseignant_id': row['enseignant__external_id'],
            'enseignant': (
                f"{row['enseignant__nom']} {row['enseignant__prenom']}"
            ),
            'module_id': row['module__external_id'],
            'module': row['module__intitule'],
            'total_seances': row['total_seances'],
            'nb_seances_cloturees': row['nb_seances_cloturees'],
            'nb_seances_non_assurees': row['nb_seances_non_assurees'],
            'taux_assiduite': attendance_rate(attended, total_presences),
            'taux_realisation': attendance_rate(
                row['nb_seances_cloturees'],
                row['total_seances'],
            ),
        })

    return by_enseignant


def build_student_absence_details(
    presence_queryset,
    seuil_alerte,
    seuil_exclusion,
):
    rows = (
        presence_queryset.values(
            'etudiant__external_id',
            'etudiant__matricule',
            'etudiant__nom',
            'etudiant__prenom',
            'etudiant__groupe__external_id',
            'etudiant__groupe__numero',
            'etudiant__groupe__annee_etude',
            'etudiant__groupe__specialite',
            'seance__module__external_id',
            'seance__module__intitule',
        )
        .annotate(
            absences_non_justifiees=Count(
                'id',
                filter=Q(statut_presence=ABSENT),
            ),
            total_presences=Count('id'),
            presents=Count(
                'id',
                filter=Q(statut_presence=PRESENT),
            ),
            justifies=Count(
                'id',
                filter=Q(statut_presence=JUSTIFIE),
            ),
        )
        .annotate(attended=F('presents') + F('justifies'))
        .order_by(
            'etudiant__nom',
            'etudiant__prenom',
            'seance__module__intitule',
        )
    )

    students = {}
    for row in rows:
        student_id = row['etudiant__external_id']
        absences = row['absences_non_justifiees']

        if student_id not in students:
            students[student_id] = {
                'etudiant_id': student_id,
                'matricule': row['etudiant__matricule'],
                'nom': row['etudiant__nom'],
                'prenom': row['etudiant__prenom'],
                'groupe_id': row['etudiant__groupe__external_id'],
                'groupe': (
                    f"{row['etudiant__groupe__specialite']} - Groupe "
                    f"{row['etudiant__groupe__numero']} "
                    f"(Année {row['etudiant__groupe__annee_etude']})"
                ),
                'module_id': row['seance__module__external_id'],
                'module': row['seance__module__intitule'],
                'absences_non_justifiees': absences,
                'total_absences': absences,
                'total_presences': row['total_presences'],
                'presents': row['presents'],
                'justifies': row['justifies'],
                'attended': row['attended'],
            }
            continue

        student = students[student_id]
        student['total_absences'] += absences
        student['total_presences'] += row['total_presences']
        student['presents'] += row['presents']
        student['justifies'] += row['justifies']
        student['attended'] += row['attended']

        if absences > student['absences_non_justifiees']:
            student['module_id'] = row['seance__module__external_id']
            student['module'] = row['seance__module__intitule']
            student['absences_non_justifiees'] = absences

    details = []
    for student in students.values():
        absences = student['absences_non_justifiees']
        if absences >= seuil_exclusion:
            niveau_alerte = 'danger'
        elif absences >= seuil_alerte:
            niveau_alerte = 'warning'
        else:
            niveau_alerte = 'normal'

        student['niveau_alerte'] = niveau_alerte
        student['taux_assiduite'] = attendance_rate(
            student['attended'],
            student['total_presences'],
        )
        details.append(student)

    details.sort(
        key=lambda item: (
            -item['absences_non_justifiees'],
            item['nom'],
            item['prenom'],
        )
    )
    return details


def build_students_at_risk(presence_queryset, seuil_alerte, seuil_exclusion):
    rows = (
        presence_queryset.filter(statut_presence=ABSENT)
        .values(
            'etudiant__external_id',
            'etudiant__matricule',
            'etudiant__nom',
            'etudiant__prenom',
            'etudiant__groupe__external_id',
            'etudiant__groupe__numero',
            'etudiant__groupe__annee_etude',
            'etudiant__groupe__specialite',
            'seance__module__external_id',
            'seance__module__intitule',
        )
        .annotate(absences_non_justifiees=Count('id'))
        .filter(absences_non_justifiees__gte=seuil_alerte)
        .order_by(
            '-absences_non_justifiees',
            'etudiant__nom',
            'etudiant__prenom',
            'seance__module__intitule',
        )
    )

    students_at_risk = []
    alert_students = set()
    exclusion_students = set()

    for row in rows:
        absences = row['absences_non_justifiees']
        niveau_alerte = (
            'danger' if absences >= seuil_exclusion else 'warning'
        )

        alert_students.add(row['etudiant__external_id'])
        if absences >= seuil_exclusion:
            exclusion_students.add(row['etudiant__external_id'])

        students_at_risk.append({
            'etudiant_id': row['etudiant__external_id'],
            'matricule': row['etudiant__matricule'],
            'nom': row['etudiant__nom'],
            'prenom': row['etudiant__prenom'],
            'groupe_id': row['etudiant__groupe__external_id'],
            'groupe': (
                f"{row['etudiant__groupe__specialite']} - Groupe "
                f"{row['etudiant__groupe__numero']} "
                f"(Année {row['etudiant__groupe__annee_etude']})"
            ),
            'module_id': row['seance__module__external_id'],
            'module': row['seance__module__intitule'],
            'absences_non_justifiees': absences,
            'niveau_alerte': niveau_alerte,
        })

    return students_at_risk, len(alert_students), len(exclusion_students)
