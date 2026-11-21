from django.shortcuts import render

# Create your views here.
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.permissions import IsAdmin, IsAdminOrSupervisorReadOnly

from .models import Role, User
from .serializers import MeSerializer, UserSerializer


def base_queryset(request):
    """Filtres : ?role=  ?status=  ?q= (email, nom, prénom, matricule)"""
    qs = User.objects.select_related("student_profile", "teacher_profile")
    params = request.query_params
    if params.get("role"):
        qs = qs.filter(role=params["role"])
    if params.get("status"):
        qs = qs.filter(status=params["status"])
    q = params.get("q")
    if q:
        qs = qs.filter(
            Q(email__icontains=q)
            | Q(first_name__icontains=q)
            | Q(last_name__icontains=q)
            | Q(student_profile__matricule__icontains=q)
        )
    return qs


class UserViewSet(viewsets.ModelViewSet):
    """CRUD complet des utilisateurs (admin) / lecture seule (superviseur)."""

    serializer_class = UserSerializer
    permission_classes = [IsAdminOrSupervisorReadOnly]

    def get_queryset(self):
        return base_queryset(self.request)

    def perform_destroy(self, instance):
        instance.soft_delete()  # TODO étape 6 : publier user.deactivated

    @action(detail=True, methods=["patch"], permission_classes=[IsAdmin])
    def activate(self, request, pk=None):
        user = self.get_object()
        user.activate()
        return Response(self.get_serializer(user).data)

    @action(detail=True, methods=["patch"], permission_classes=[IsAdmin])
    def deactivate(self, request, pk=None):
        user = self.get_object()
        user.deactivate()  # TODO étape 6 : publier user.deactivated
        return Response(self.get_serializer(user).data)

    @action(detail=False, methods=["get", "patch"], permission_classes=[IsAuthenticated])
    def me(self, request):
        try:
            user = User.objects.select_related("student_profile", "teacher_profile").get(
                pk=request.user.id
            )
        except (User.DoesNotExist, DjangoValidationError):
            raise NotFound("Profil introuvable.")
        if request.method == "GET":
            return Response(MeSerializer(user).data)
        forbidden = set(request.data) - {"language", "phone"}          
        if forbidden:                                                   
            raise ValidationError({f: "Champ non modifiable." for f in forbidden})  
        serializer = MeSerializer(user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class _RoleReadOnlyViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    serializer_class = UserSerializer
    permission_classes = [IsAdminOrSupervisorReadOnly]
    role = None

    def get_queryset(self):
        return base_queryset(self.request).filter(role=self.role)


class StudentViewSet(_RoleReadOnlyViewSet):
    role = Role.STUDENT


class TeacherViewSet(_RoleReadOnlyViewSet):
    role = Role.TEACHER
