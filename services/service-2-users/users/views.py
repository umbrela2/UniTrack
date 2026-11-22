from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.messaging.events import UserEvents
from core.messaging.publisher import publish_user_event
from core.permissions import IsAdmin, IsAdminOrSupervisorReadOnly

from .models import Role, User
from .serializers import MeSerializer, UserSerializer


def base_queryset(request, deleted=False):
    """Filtres : ?role=  ?status=  ?q= (email, nom, prénom, matricule)
    deleted=True : uniquement les comptes supprimés (soft delete)."""
    manager = User.all_objects if deleted else User.objects
    qs = manager.select_related("student_profile", "teacher_profile")
    if deleted:
        qs = qs.filter(deleted_at__isnull=False)
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
        # comptes supprimés : visibles seulement via ?deleted=true (liste) et pour restore
        wants_deleted = self.action == "restore" or (
            self.action == "list" and self.request.query_params.get("deleted") == "true"
        )
        return base_queryset(self.request, deleted=wants_deleted)

    def perform_destroy(self, instance):
        instance.soft_delete()
        publish_user_event(UserEvents.DELETED, instance)

    @action(detail=True, methods=["patch"], permission_classes=[IsAdmin])
    def activate(self, request, pk=None):
        user = self.get_object()
        user.activate()
        publish_user_event(UserEvents.ACTIVATED, user)
        return Response(self.get_serializer(user).data)

    @action(detail=True, methods=["patch"], permission_classes=[IsAdmin])
    def deactivate(self, request, pk=None):
        user = self.get_object()
        user.deactivate()
        publish_user_event(UserEvents.DEACTIVATED, user)
        return Response(self.get_serializer(user).data)

    @action(detail=True, methods=["post"], permission_classes=[IsAdmin])
    def restore(self, request, pk=None):
        """Restaure un compte supprimé (même id, même historique)."""
        user = self.get_object()
        user.restore()
        publish_user_event(UserEvents.ACTIVATED, user)  # S1 réactive la connexion
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
        publish_user_event(UserEvents.UPDATED, user)  # la langue sert à S5 (emails)
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
