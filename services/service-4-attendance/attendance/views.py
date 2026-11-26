import csv
from datetime import timedelta

from django.db.models import Count, Q
from django.http import HttpResponse
from django.utils import timezone
from django.utils.dateparse import parse_date
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from . import services
from .auth import ADMIN, ENSEIGNANT, ETUDIANT, SUPERVISEUR, role_required
from .models import AttendanceSettings, Enrollment, Presence, PresenceStatus, Seance, SeanceStatus
from .serializers import (CheckInSerializer, ManualPresenceSerializer, PresenceRecordSerializer, SeanceSerializer,
                          SettingsSerializer)


class CheckinThrottle(UserRateThrottle):
    scope = "checkin"


def _date(request, name):
    raw = request.query_params.get(name)
    if not raw:
        return None
    d = parse_date(raw)
    if d is None:
        raise ValidationError({name: "Format attendu : AAAA-MM-JJ."})
    return d


def build_roster(seance):
    enrolled = Enrollment.objects.filter(group_id=seance.group_id)
    pres = {p.student_id: p for p in seance.presences.all()}
    rows, present, absent = [], 0, 0
    for e in enrolled:
        p = pres.get(e.student_id)
        if p and p.statut == PresenceStatus.PRESENT:
            present += 1
        elif p:
            absent += 1
        rows.append({"student_id": e.student_id, "matricule": e.matricule, "nom": e.nom, "prenom": e.prenom,
                     "statut": p.statut if p else None, "mode": p.mode if p else None,
                     "date_enregistrement": p.date_enregistrement if p else None})
    total = len(rows)
    return {"seance": SeanceSerializer(seance).data,
            "summary": {"total": total, "presents": present, "absents": absent, "en_attente": total - present - absent},
            "students": rows}


class SeanceViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = SeanceSerializer
    lookup_value_regex = r"\d+"
    ROLES = {
        "start": [ENSEIGNANT], "close": [ENSEIGNANT], "regenerate_code": [ENSEIGNANT], "code": [ENSEIGNANT],
        "manual": [ENSEIGNANT], "check_in": [ETUDIANT], "current": [ETUDIANT],
        "non_assurees": [ADMIN, SUPERVISEUR], "presences": [ENSEIGNANT, ADMIN, SUPERVISEUR],
        "export": [ENSEIGNANT, ADMIN, SUPERVISEUR],
    }

    def get_permissions(self):
        roles = self.ROLES.get(self.action)
        return [role_required(*roles)()] if roles else [IsAuthenticated()]

    def get_queryset(self):
        u, qs = self.request.user, Seance.objects.all()
        if u.role == ENSEIGNANT:
            qs = qs.filter(enseignant_id=u.id)
        elif u.role == ETUDIANT:
            qs = qs.filter(group_id__in=Enrollment.objects.filter(student_id=u.id).values("group_id"))
        return qs

    def _filtered(self, qs):
        r = self.request
        for param, field in (("statut", "statut"), ("group_id", "group_id"), ("module_id", "module_id")):
            if r.query_params.get(param):
                qs = qs.filter(**{field: r.query_params[param]})
        if r.query_params.get("enseignant_id") and r.user.role in (ADMIN, SUPERVISEUR):
            qs = qs.filter(enseignant_id=r.query_params["enseignant_id"])
        if _date(r, "date_from"):
            qs = qs.filter(date_seance__gte=_date(r, "date_from"))
        if _date(r, "date_to"):
            qs = qs.filter(date_seance__lte=_date(r, "date_to"))
        return qs

    def filter_queryset(self, queryset):
        return self._filtered(queryset) if self.action in ("list", "non_assurees") else queryset

    def _page(self, qs):
        page = self.paginate_queryset(qs)
        return self.get_paginated_response(self.get_serializer(page, many=True).data)

    # --- consultation ------------------------------------------------------
    @action(detail=False, methods=["get"])
    def today(self, request):
        """Séances du jour (enseignant : à démarrer ; étudiant : de son groupe)."""
        return Response(self.get_serializer(self.get_queryset().filter(date_seance=timezone.localdate()),
                                            many=True).data)

    @action(detail=False, methods=["get"])
    def current(self, request):
        """Étudiant : séances en cours de son groupe (pour saisir le code)."""
        return Response(self.get_serializer(self.get_queryset().filter(statut=SeanceStatus.EN_COURS),
                                            many=True).data)

    @action(detail=False, methods=["get"], url_path="non-assurees")
    def non_assurees(self, request):
        """FP13 / UC-ADMIN-04 : séances non assurées (date, module, enseignant, groupe)."""
        return self._page(self.filter_queryset(self.get_queryset().filter(statut=SeanceStatus.NON_ASSUREE))
                          .order_by("-date_seance", "-heure_debut"))

    # --- enseignant --------------------------------------------------------
    @action(detail=True, methods=["post"])
    def start(self, request, pk=None):
        s = services.start_seance(pk, request.user)
        return Response({**SeanceSerializer(s).data, "code": s.code_presence,
                         "code_expires_at": s.code_expires_at}, status=status.HTTP_200_OK)

    @action(detail=True, methods=["get"])
    def code(self, request, pk=None):
        s = self.get_object()
        if s.statut != SeanceStatus.EN_COURS:
            return Response({"error": "session_not_active", "detail": "La séance n'est pas en cours."}, status=409)
        remaining = max(0, int((s.code_expires_at - timezone.now()).total_seconds()))
        return Response({"code": s.code_presence, "code_expires_at": s.code_expires_at,
                         "seconds_remaining": remaining, "expired": remaining == 0})

    @action(detail=True, methods=["post"], url_path="regenerate-code")
    def regenerate_code(self, request, pk=None):
        s = services.regenerate_code(pk, request.user)
        return Response({"code": s.code_presence, "code_expires_at": s.code_expires_at})

    @action(detail=True, methods=["get"])
    def presences(self, request, pk=None):
        return Response(build_roster(self.get_object()))

    @action(detail=True, methods=["put"], url_path=r"presences/(?P<student_id>[^/.]+)")
    def manual(self, request, pk=None, student_id=None):
        ser = ManualPresenceSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        p = services.manual_set_presence(pk, request.user, student_id, ser.validated_data["statut"])
        return Response({"student_id": p.student_id, "statut": p.statut, "mode": p.mode,
                         "date_enregistrement": p.date_enregistrement})

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        s = services.close_seance(pk, request.user)
        return Response(build_roster(s))

    @action(detail=True, methods=["get"])
    def export(self, request, pk=None):
        roster = build_roster(self.get_object())
        resp = HttpResponse(content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = f'attachment; filename="presences_seance_{pk}.csv"'
        resp.write("\ufeff")
        w = csv.writer(resp)
        w.writerow(["matricule", "nom", "prenom", "statut", "mode", "date_enregistrement"])
        for r in roster["students"]:
            w.writerow([r["matricule"], r["nom"], r["prenom"], r["statut"] or "EN_ATTENTE", r["mode"] or "",
                        r["date_enregistrement"] or ""])
        return resp

    # --- étudiant ----------------------------------------------------------
    @action(detail=True, methods=["post"], url_path="check-in", throttle_classes=[CheckinThrottle])
    def check_in(self, request, pk=None):
        ser = CheckInSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        p = services.check_in(pk, request.user, **ser.validated_data)
        return Response({"statut": p.statut, "date_enregistrement": p.date_enregistrement,
                         "message": "Présence enregistrée."}, status=status.HTTP_201_CREATED)


class MyAttendanceView(APIView):
    permission_classes = [role_required(ETUDIANT)]

    @extend_schema(responses=dict)
    def get(self, request):
        """UC-ETU-02 : assiduité par module (filtres module_id, date_from, date_to ; details=1 pour le détail)."""
        mod, d1, d2 = request.query_params.get("module_id"), _date(request, "date_from"), _date(request, "date_to")
        data = services.student_summary(request.user.id, mod, d1, d2)
        if request.query_params.get("details") == "1":
            qs = Presence.objects.filter(student_id=request.user.id).select_related("seance")
            if mod:
                qs = qs.filter(seance__module_id=mod)
            if d1:
                qs = qs.filter(seance__date_seance__gte=d1)
            if d2:
                qs = qs.filter(seance__date_seance__lte=d2)
            qs = qs.order_by("-seance__date_seance", "-seance__heure_debut")[:200]
            data["records"] = PresenceRecordSerializer(qs, many=True).data
        return Response(data)


class MyAlertsView(APIView):
    permission_classes = [role_required(ETUDIANT)]

    @extend_schema(responses=dict)
    def get(self, request):
        """« Mes alertes » : modules à 3 absences (orange) ou 5 (rouge) – seuils configurables."""
        data = services.student_summary(request.user.id)
        alerts = [m for m in data["modules"] if m["niveau_alerte"] != "vert"]
        return Response({"seuils": data["seuils"], "alertes": alerts})


class HistoryView(APIView):
    """UC-ADMIN-04 : historique d'assiduité filtrable (période, groupe, module, enseignant, étudiant)."""
    permission_classes = [role_required(ADMIN, SUPERVISEUR)]

    @extend_schema(responses=dict)
    def get(self, request):
        qs = Presence.objects.select_related("seance").order_by("-seance__date_seance", "-seance__heure_debut", "id")
        q = request.query_params
        for param, field in (("group_id", "seance__group_id"), ("module_id", "seance__module_id"),
                             ("enseignant_id", "seance__enseignant_id"), ("student_id", "student_id"),
                             ("statut", "statut")):
            if q.get(param):
                qs = qs.filter(**{field: q[param]})
        if _date(request, "date_from"):
            qs = qs.filter(seance__date_seance__gte=_date(request, "date_from"))
        if _date(request, "date_to"):
            qs = qs.filter(seance__date_seance__lte=_date(request, "date_to"))
        from rest_framework.pagination import PageNumberPagination
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(qs, request)
        names = {e.student_id: e for e in Enrollment.objects.filter(student_id__in=[p.student_id for p in page])}
        rows = PresenceRecordSerializer(page, many=True).data
        for r in rows:
            e = names.get(r["student_id"])
            r["student_nom"] = f"{e.prenom} {e.nom}".strip() if e else ""
            r["matricule"] = e.matricule if e else ""
        return paginator.get_paginated_response(rows)


class DashboardView(APIView):
    """Tableau de bord (enseignant : ses séances ; admin/superviseur : global). 30 derniers jours par défaut."""
    permission_classes = [role_required(ENSEIGNANT, ADMIN, SUPERVISEUR)]

    @extend_schema(responses=dict)
    def get(self, request):
        d2 = _date(request, "date_to") or timezone.localdate()
        d1 = _date(request, "date_from") or d2 - timedelta(days=30)
        seances = Seance.objects.filter(date_seance__range=(d1, d2))
        if request.user.role == ENSEIGNANT:
            seances = seances.filter(enseignant_id=request.user.id)
        by_status = {r["statut"]: r["n"] for r in seances.values("statut").annotate(n=Count("id"))}
        agg = Presence.objects.filter(seance__in=seances).aggregate(
            presents=Count("id", filter=Q(statut=PresenceStatus.PRESENT)),
            absents=Count("id", filter=Q(statut=PresenceStatus.ABSENT)))
        total = agg["presents"] + agg["absents"]
        return Response({
            "periode": {"du": d1, "au": d2},
            "seances_par_statut": by_status,
            "seances_aujourdhui": seances.filter(date_seance=timezone.localdate()).count(),
            "seances_non_assurees": by_status.get(SeanceStatus.NON_ASSUREE, 0),
            "presences": {**agg, "taux_assiduite": round(100 * agg["presents"] / total, 1) if total else None}})


class SettingsView(APIView):
    permission_classes = [role_required(ADMIN)]

    @extend_schema(responses=SettingsSerializer)
    def get(self, request):
        return Response(SettingsSerializer(AttendanceSettings.get()).data)

    @extend_schema(request=SettingsSerializer, responses=SettingsSerializer)
    def put(self, request):
        ser = SettingsSerializer(AttendanceSettings.get(), data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data)

    patch = put
