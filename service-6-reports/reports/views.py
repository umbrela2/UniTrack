from django.db.models import Count, F, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.views.generic import TemplateView
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from .exporters import build_excel_report, build_pdf_report
from .models import Etudiant, Groupe, Module, Presence, Seance
from .sync import process_sync_payload
from .utils import (
    ABSENT,
    JUSTIFIE,
    PRESENT,
    apply_role_filter,
    attendance_rate,
    build_attendance_totals,
    build_by_enseignant,
    build_by_groupe,
    build_by_module,
    build_student_absence_details,
    build_students_at_risk,
    filter_sessions,
    get_active_thresholds,
)

DASHBOARD_PARAMETERS = [
    OpenApiParameter(
        'module_id',
        OpenApiTypes.INT,
        OpenApiParameter.QUERY,
        description='Identifiant externe du module.',
    ),
    OpenApiParameter(
        'groupe_id',
        OpenApiTypes.INT,
        OpenApiParameter.QUERY,
        description='Identifiant externe du groupe.',
    ),
    OpenApiParameter(
        'enseignant_id',
        OpenApiTypes.INT,
        OpenApiParameter.QUERY,
        description='Identifiant externe de l\'enseignant.',
    ),
    OpenApiParameter(
        'date_from',
        OpenApiTypes.DATE,
        OpenApiParameter.QUERY,
        description='Date minimale de la séance (YYYY-MM-DD).',
    ),
    OpenApiParameter(
        'date_to',
        OpenApiTypes.DATE,
        OpenApiParameter.QUERY,
        description='Date maximale de la séance (YYYY-MM-DD).',
    ),
    OpenApiParameter(
        'role',
        OpenApiTypes.STR,
        OpenApiParameter.QUERY,
        enum=['admin', 'superviseur', 'enseignant', 'etudiant'],
        description='Rôle utilisé pour restreindre le périmètre des données.',
    ),
    OpenApiParameter(
        'user_id',
        OpenApiTypes.INT,
        OpenApiParameter.QUERY,
        description='Identifiant externe de l\'enseignant (rôle enseignant).',
    ),
    OpenApiParameter(
        'matricule',
        OpenApiTypes.STR,
        OpenApiParameter.QUERY,
        description='Matricule de l\'étudiant (rôle etudiant).',
    ),
]

NON_ASSURED_PARAMETERS = [
    OpenApiParameter(
        'date_from',
        OpenApiTypes.DATE,
        OpenApiParameter.QUERY,
        description='Date minimale de la séance (YYYY-MM-DD).',
    ),
    OpenApiParameter(
        'date_to',
        OpenApiTypes.DATE,
        OpenApiParameter.QUERY,
        description='Date maximale de la séance (YYYY-MM-DD).',
    ),
    OpenApiParameter(
        'module_id',
        OpenApiTypes.INT,
        OpenApiParameter.QUERY,
        description='Identifiant externe du module.',
    ),
    OpenApiParameter(
        'enseignant_id',
        OpenApiTypes.INT,
        OpenApiParameter.QUERY,
        description='Identifiant externe de l\'enseignant.',
    ),
    OpenApiParameter(
        'groupe_id',
        OpenApiTypes.INT,
        OpenApiParameter.QUERY,
        description='Identifiant externe du groupe.',
    ),
]


class HealthView(APIView):
    @extend_schema(
        responses={
            200: {
                'type': 'object',
                'properties': {
                    'service': {'type': 'string'},
                    'status': {'type': 'string'},
                    'port': {'type': 'integer'},
                },
            }
        }
    )
    def get(self, request):
        return Response(
            {
                'service': 'S6: Statistics & Reports',
                'status': 'ok',
                'port': 8006,
            }
        )


class DashboardSummaryView(APIView):
    @extend_schema(
        parameters=DASHBOARD_PARAMETERS,
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        params = request.query_params
        seuil_alerte, seuil_exclusion = get_active_thresholds()

        sessions = Seance.objects.select_related(
            'module',
            'groupe',
            'enseignant',
            'salle',
        )
        sessions = filter_sessions(sessions, params)
        sessions = apply_role_filter(sessions, params)

        closed_sessions = sessions.filter(statut=Seance.Statut.CLOTUREE)
        non_assured_count = sessions.filter(
            statut=Seance.Statut.NON_ASSURREE
        ).count()

        presences = Presence.objects.filter(
            seance__in=closed_sessions
        ).select_related(
            'seance__module',
            'seance__groupe',
            'etudiant__groupe',
        )

        totals = build_attendance_totals(presences)
        by_module = build_by_module(closed_sessions, presences)
        by_groupe = build_by_groupe(closed_sessions, presences)
        by_enseignant = build_by_enseignant(sessions, presences)
        students_at_risk, alert_count, exclusion_count = build_students_at_risk(
            presences,
            seuil_alerte,
            seuil_exclusion,
        )
        students_detail = build_student_absence_details(
            presences,
            seuil_alerte,
            seuil_exclusion,
        )

        group_scope_params = params.copy()
        group_scope_params.pop('groupe_id', None)
        group_scope_sessions = Seance.objects.select_related(
            'module',
            'groupe',
            'enseignant',
            'salle',
        )
        group_scope_sessions = filter_sessions(
            group_scope_sessions,
            group_scope_params,
        )
        group_scope_sessions = apply_role_filter(
            group_scope_sessions,
            group_scope_params,
        )
        group_scope_closed = group_scope_sessions.filter(
            statut=Seance.Statut.CLOTUREE
        )
        group_scope_presences = Presence.objects.filter(
            seance__in=group_scope_closed
        )
        group_rows = build_by_groupe(
            group_scope_closed,
            group_scope_presences,
        )
        group_totals = build_attendance_totals(group_scope_presences)
        group_row_map = {
            row['groupe_id']: row
            for row in group_rows
        }
        group_cards = [
            {
                'groupe_id': None,
                'groupe': 'Tous',
                'taux_assiduite': group_totals['taux_assiduite'],
                'total_absences': group_totals['absents'],
                'nb_seances': sum(
                    row['nb_seances'] for row in group_rows
                ),
            }
        ]
        for groupe in Groupe.objects.all():
            group_row = group_row_map.get(groupe.external_id)
            group_cards.append({
                'groupe_id': groupe.external_id,
                'groupe': str(groupe),
                'taux_assiduite': (
                    group_row['taux_assiduite'] if group_row else 0.0
                ),
                'total_absences': (
                    group_row['total_absences'] if group_row else 0
                ),
                'nb_seances': (
                    group_row['nb_seances'] if group_row else 0
                ),
            })

        return Response({
            'kpis': {
                'total_seances_cloturees': closed_sessions.count(),
                'total_seances_non_assurees': non_assured_count,
                'taux_assiduite_global': totals['taux_assiduite'],
                'total_absences_non_justifiees': totals['absents'],
                'etudiants_en_alerte_count': alert_count,
                'etudiants_en_exclusion_count': exclusion_count,
            },
            'by_module': by_module,
            'by_groupe': by_groupe,
            'by_enseignant': by_enseignant,
            'group_cards': group_cards,
            'students_at_risk': students_at_risk,
            'students_detail': students_detail,
            'presence_breakdown': {
                'presents': totals['presents'],
                'absents': totals['absents'],
                'justifies': totals['justifies'],
            },
            'seuils': {
                'alerte': seuil_alerte,
                'exclusion': seuil_exclusion,
            },
        })


class DashboardPageView(TemplateView):
    template_name = 'reports/dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['groupes'] = Groupe.objects.all()
        context['modules'] = Module.objects.all()
        return context


class NonAssuredSessionsView(APIView):
    @extend_schema(
        parameters=NON_ASSURED_PARAMETERS,
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        sessions = Seance.objects.select_related(
            'module',
            'groupe',
            'enseignant',
            'salle',
        ).filter(statut=Seance.Statut.NON_ASSURREE)
        sessions = filter_sessions(sessions, request.query_params)
        sessions = sessions.order_by('-date_seance', 'heure_debut')

        data = [
            {
                'id': seance.external_id,
                'date_seance': seance.date_seance.isoformat(),
                'heure_debut': seance.heure_debut.strftime('%H:%M'),
                'heure_fin': seance.heure_fin.strftime('%H:%M'),
                'type_seance': seance.type_seance,
                'module': seance.module.intitule,
                'module_id': seance.module.external_id,
                'enseignant': (
                    f'{seance.enseignant.nom} {seance.enseignant.prenom}'
                ),
                'enseignant_id': seance.enseignant.external_id,
                'groupe': str(seance.groupe),
                'groupe_id': seance.groupe.external_id,
                'salle': seance.salle.nom_salle,
                'salle_id': seance.salle.external_id,
            }
            for seance in sessions
        ]

        return Response(data)


class StudentStatsView(APIView):
    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request, matricule):
        etudiant = get_object_or_404(
            Etudiant.objects.select_related('groupe'),
            matricule=matricule,
        )
        seuil_alerte, seuil_exclusion = get_active_thresholds()

        presences = Presence.objects.filter(
            etudiant=etudiant,
            seance__statut=Seance.Statut.CLOTUREE,
        ).select_related('seance__module')

        totals = presences.aggregate(
            total=Count('id'),
            presents=Count('id', filter=Q(statut_presence=PRESENT)),
            justifies=Count('id', filter=Q(statut_presence=JUSTIFIE)),
            absents=Count('id', filter=Q(statut_presence=ABSENT)),
        )
        attended = totals['presents'] + totals['justifies']

        module_sessions = (
            Seance.objects.filter(
                groupe=etudiant.groupe,
                statut=Seance.Statut.CLOTUREE,
            )
            .values('module__external_id', 'module__intitule')
            .annotate(total_seances=Count('id'))
        )
        module_presences = (
            presences.values(
                'seance__module__external_id',
                'seance__module__intitule',
            )
            .annotate(
                presents=Count(
                    'id',
                    filter=Q(statut_presence=PRESENT),
                ),
                absents_non_justifies=Count(
                    'id',
                    filter=Q(statut_presence=ABSENT),
                ),
                justifies=Count(
                    'id',
                    filter=Q(statut_presence=JUSTIFIE),
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
            presents_count = presence_row['presents'] if presence_row else 0
            absents_count = (
                presence_row['absents_non_justifies']
                if presence_row
                else 0
            )
            justifies_count = (
                presence_row['justifies'] if presence_row else 0
            )
            module_attended = presence_row['attended'] if presence_row else 0
            total_seances = row['total_seances']

            if absents_count >= seuil_exclusion:
                statut_alerte = 'danger'
            elif absents_count >= seuil_alerte:
                statut_alerte = 'warning'
            else:
                statut_alerte = 'ok'

            by_module.append({
                'module_id': module_id,
                'module': row['module__intitule'],
                'total_seances': total_seances,
                'presents': presents_count,
                'absents_non_justifies': absents_count,
                'justifies': justifies_count,
                'taux_assiduite': attendance_rate(
                    module_attended,
                    total_seances,
                ),
                'statut_alerte': statut_alerte,
            })

        return Response({
            'etudiant': {
                'external_id': etudiant.external_id,
                'matricule': etudiant.matricule,
                'nom': etudiant.nom,
                'prenom': etudiant.prenom,
                'email': etudiant.email,
                'groupe_id': etudiant.groupe.external_id,
                'groupe': str(etudiant.groupe),
            },
            'taux_assiduite_global': attendance_rate(
                attended,
                totals['total'],
            ),
            'total_absences_non_justifiees': totals['absents'],
            'by_module': by_module,
        })


class SyncView(APIView):
    @extend_schema(
        request=OpenApiTypes.OBJECT,
        responses={200: OpenApiTypes.OBJECT},
    )
    def post(self, request):
        result = process_sync_payload(request.data)
        return Response({
            'status': 'ok',
            **result,
        })


EXPORT_PARAMETERS = [
    OpenApiParameter(
        'report_type',
        OpenApiTypes.STR,
        OpenApiParameter.QUERY,
        enum=[
            'attendance_summary',
            'students_at_risk',
            'non_assured_sessions',
        ],
        description='Type de rapport à exporter.',
    ),
    OpenApiParameter(
        'module_id',
        OpenApiTypes.INT,
        OpenApiParameter.QUERY,
        description='Identifiant externe du module.',
    ),
    OpenApiParameter(
        'groupe_id',
        OpenApiTypes.INT,
        OpenApiParameter.QUERY,
        description='Identifiant externe du groupe.',
    ),
    OpenApiParameter(
        'enseignant_id',
        OpenApiTypes.INT,
        OpenApiParameter.QUERY,
        description='Identifiant externe de l\'enseignant.',
    ),
    OpenApiParameter(
        'date_from',
        OpenApiTypes.DATE,
        OpenApiParameter.QUERY,
        description='Date minimale de la séance (YYYY-MM-DD).',
    ),
    OpenApiParameter(
        'date_to',
        OpenApiTypes.DATE,
        OpenApiParameter.QUERY,
        description='Date maximale de la séance (YYYY-MM-DD).',
    ),
]


class ExcelExportView(APIView):
    @extend_schema(
        parameters=EXPORT_PARAMETERS,
        responses={200: OpenApiTypes.BINARY},
    )
    def get(self, request):
        content = build_excel_report(request.query_params).getvalue()
        response = HttpResponse(
            content,
            content_type=(
                'application/vnd.openxmlformats-officedocument.'
                'spreadsheetml.sheet'
            ),
        )
        response['Content-Disposition'] = (
            'attachment; filename="unitrack_report.xlsx"'
        )
        response['Content-Length'] = str(len(content))
        return response


class PdfExportView(APIView):
    @extend_schema(
        parameters=EXPORT_PARAMETERS,
        responses={200: OpenApiTypes.BINARY},
    )
    def get(self, request):
        content = build_pdf_report(request.query_params).getvalue()
        response = HttpResponse(content, content_type='application/pdf')
        response['Content-Disposition'] = (
            'attachment; filename="unitrack_report.pdf"'
        )
        response['Content-Length'] = str(len(content))
        return response
