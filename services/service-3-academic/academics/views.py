from datetime import date, timedelta

from django.utils.dateparse import parse_date
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from .auth import IsAdminOrReadOnly, IsAdminOrSupervisor, IsAdminOrTeacher
from .conflicts import detect_conflicts
from .models import Departement, Groupe, Module, Salle, Seance
from .serializers import (
    ConflictCheckSerializer, DepartementSerializer, GroupeSerializer,
    ModuleSerializer, SalleSerializer, SeanceReadSerializer,
    SeanceWriteSerializer,
)
from .services import (
    distinct_labels, get_departement, get_groupe, get_salle,
)


class _StructureViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAdminOrReadOnly]


class DepartementViewSet(_StructureViewSet):
    queryset = Departement.objects.all().order_by("nom")
    serializer_class = DepartementSerializer


class GroupeViewSet(_StructureViewSet):
    queryset = Groupe.objects.select_related("departement").order_by(
        "annee_etude", "specialite", "numero"
    )
    serializer_class = GroupeSerializer


class ModuleViewSet(_StructureViewSet):
    queryset = Module.objects.select_related("departement").order_by("intitule")
    serializer_class = ModuleSerializer


class SalleViewSet(_StructureViewSet):
    queryset = Salle.objects.all().order_by("nom_salle")
    serializer_class = SalleSerializer


class StructureOptionsView(APIView):
    """Listes de suggestions pour le formulaire de seance (lecture seule).

    Le frontend s'en sert pour les datalists. Aucune donnee n'est creee ici.
    """

    permission_classes = [IsAdminOrTeacher]

    def get(self, request):
        groupes = [
            {
                "id": g.pk,
                "label": str(g),
                "departement": g.departement.nom,
                "annee_etude": g.annee_etude,
                "specialite": g.specialite,
                "numero": g.numero,
            }
            for g in Groupe.objects.select_related("departement").order_by(
                "departement__nom", "annee_etude", "specialite", "numero"
            )
        ]
        modules = [
            {
                "id": m.pk,
                "intitule": m.intitule,
                "semestre": m.semestre,
                "departement": m.departement.nom,
            }
            for m in Module.objects.select_related("departement").order_by(
                "intitule", "semestre"
            )
        ]
        return Response({
            "departements": list(
                Departement.objects.order_by("nom").values_list("nom", flat=True)
            ),
            "annees": distinct_labels(
                Groupe.objects.values_list("annee_etude", flat=True)
            ),
            "specialites": distinct_labels(
                Groupe.objects.values_list("specialite", flat=True)
            ),
            "groupes": groupes,
            "modules": modules,
            "module_intitules": distinct_labels(
                Module.objects.values_list("intitule", flat=True)
            ),
            "semestres": distinct_labels(
                Module.objects.values_list("semestre", flat=True)
            ),
            "salles": list(
                Salle.objects.order_by("nom_salle").values_list("nom_salle", flat=True)
            ),
        })


# ---------- Seances ----------
def _apply_filters(qs, params):
    if d := parse_date(params.get("date", "")):
        qs = qs.filter(date_seance=d)
    if d := parse_date(params.get("from", "")):
        qs = qs.filter(date_seance__gte=d)
    if d := parse_date(params.get("to", "")):
        qs = qs.filter(date_seance__lte=d)
    for param, field in (("groupe", "groupe_id"), ("module", "module_id"),
                         ("salle", "salle_id"), ("enseignant_id", "enseignant_id"),
                         ("statut", "statut")):
        if params.get(param):
            qs = qs.filter(**{field: params[param]})
    return qs


class SeanceViewSet(viewsets.ModelViewSet):
    """RG6 : l'enseignant ne voit et ne modifie que ses propres seances."""

    permission_classes = [IsAdminOrTeacher]

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return SeanceWriteSerializer
        return SeanceReadSerializer

    def get_queryset(self):
        qs = Seance.objects.select_related(
            "module", "groupe", "groupe__departement", "salle",
        )
        user = self.request.user
        if not user.is_admin:
            qs = qs.filter(enseignant_id=user.id)
        return _apply_filters(qs, self.request.query_params)

    def _check_editable(self, seance):
        if not self.request.user.is_admin and seance.statut != Seance.Statut.PLANIFIEE:
            raise PermissionDenied("Seance deja demarree, cloturee ou annulee : modification impossible.")

    def perform_update(self, serializer):
        self._check_editable(serializer.instance)
        serializer.save()

    def perform_destroy(self, instance):
        self._check_editable(instance)
        instance.delete()

    @action(detail=False, methods=["get"])
    def today(self, request):
        """Seances du jour (consommees par le Service 4 - Attendance)."""
        qs = self.get_queryset().filter(date_seance=date.today())
        qs = qs.exclude(statut=Seance.Statut.ANNULEE)
        return Response(SeanceReadSerializer(qs, many=True, context={"request": request}).data)

    @action(detail=False, methods=["get"], url_path="non-assurees",
            permission_classes=[IsAdminOrSupervisor])
    def non_assurees(self, request):
        """FP13 : liste des seances non assurees (Date, Module, Enseignant, Groupe)."""
        qs = _apply_filters(
            Seance.objects.select_related(
                "module", "groupe", "groupe__departement", "salle",
            ),
            request.query_params,
        ).filter(statut=Seance.Statut.NON_ASSUREE).order_by("-date_seance", "-heure_debut")
        page = self.paginate_queryset(qs)
        ser = SeanceReadSerializer(page, many=True, context={"request": request})
        return self.get_paginated_response(ser.data)


# ---------- Timetable ----------
class CheckConflictsView(APIView):
    """Dry-run : verifie les conflits sans rien enregistrer.

    Accepte les identifiants existants et/ou les libelles du formulaire. Les
    libelles sont uniquement *recherches* (jamais crees).
    """

    permission_classes = [IsAdminOrTeacher]

    def post(self, request):
        ser = ConflictCheckSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data

        if request.user.is_admin:
            if not d.get("enseignant_id"):
                raise ValidationError(
                    {"enseignant_id": "Obligatoire pour l'administrateur."}
                )
            enseignant_id = d["enseignant_id"]
        else:
            enseignant_id = request.user.id

        salle = d.get("salle")
        if salle is None and d.get("salle_nom"):
            salle = get_salle(d["salle_nom"], create=False)

        groupe = d.get("groupe")
        if groupe is None and all(
            d.get(key) for key in
            ("departement", "annee_etude", "specialite", "groupe_numero")
        ):
            departement = get_departement(d["departement"], create=False)
            if departement is not None:
                groupe = get_groupe(
                    departement, d["annee_etude"], d["specialite"],
                    d["groupe_numero"], create=False,
                )

        conflits = detect_conflicts(
            date_seance=d["date_seance"], heure_debut=d["heure_debut"],
            heure_fin=d["heure_fin"], enseignant_id=enseignant_id,
            salle=salle, groupe=groupe, exclude_id=d.get("exclude_id"),
        )
        return Response({
            "conflit": bool(conflits),
            "conflits": conflits,
            # Utile au frontend : indique si les references existent deja.
            "salle_existante": salle is not None,
            "groupe_existant": groupe is not None,
        })


class WeekView(APIView):
    """Grille hebdomadaire (dimanche -> samedi) pour le calendrier Bootstrap.

    Parametres : date (une date de la semaine, defaut aujourd'hui),
    enseignant_id OU groupe. Un enseignant voit par defaut sa propre semaine.
    """

    permission_classes = [IsAdminOrTeacher]

    def get(self, request):
        ref = parse_date(request.query_params.get("date", "")) or date.today()
        debut = ref - timedelta(days=(ref.weekday() + 1) % 7)  # dimanche
        fin = debut + timedelta(days=6)

        qs = Seance.objects.select_related(
            "module", "groupe", "groupe__departement", "salle",
        ).filter(date_seance__range=(debut, fin)).exclude(statut=Seance.Statut.ANNULEE)

        groupe = request.query_params.get("groupe")
        ens = request.query_params.get("enseignant_id")
        if groupe:
            qs = qs.filter(groupe_id=groupe)
        elif request.user.is_admin:
            if not ens:
                raise ValidationError("Precisez enseignant_id ou groupe.")
            qs = qs.filter(enseignant_id=ens)
        else:
            qs = qs.filter(enseignant_id=request.user.id)

        jours = {(debut + timedelta(days=i)).isoformat(): [] for i in range(7)}
        for s in qs.order_by("date_seance", "heure_debut"):
            jours[s.date_seance.isoformat()].append(
                SeanceReadSerializer(s, context={"request": request}).data
            )
        return Response({"semaine_debut": debut, "semaine_fin": fin, "jours": jours})
