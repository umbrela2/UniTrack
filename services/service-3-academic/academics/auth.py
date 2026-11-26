"""Authentification par JWT emis par le Service 1 + controle d'acces par role.

Hypothese a valider avec l'equipe Service 1 : le token contient les claims
configures dans .env (JWT_USER_ID_CLAIM / JWT_ROLE_CLAIM, par defaut
`user_id` et `role`). Roles reconnus : voir ROLE_* ci-dessous.
"""
from dataclasses import dataclass

import jwt
from django.conf import settings
from rest_framework import exceptions, permissions
from rest_framework.authentication import BaseAuthentication

ROLE_ADMIN = {"admin", "administrateur"}
ROLE_TEACHER = {"enseignant", "teacher"}
ROLE_STUDENT = {"etudiant", "student"}
ROLE_SUPERVISOR = {"superviseur", "supervisor"}


@dataclass
class AuthUser:
    id: int
    role: str
    is_authenticated: bool = True

    @property
    def is_admin(self):
        return self.role in ROLE_ADMIN

    @property
    def is_teacher(self):
        return self.role in ROLE_TEACHER

    @property
    def is_supervisor(self):
        return self.role in ROLE_SUPERVISOR


class JWTAuthentication(BaseAuthentication):
    def authenticate_header(self, request):
        return "Bearer"

    def authenticate(self, request):
        header = request.headers.get("Authorization", "")
        if header.lower().startswith("bearer "):
            return self._from_token(header.split(" ", 1)[1].strip())

        # Mode developpement uniquement (Postman, tests)
        if settings.AUTH_DEV_MODE and request.headers.get("X-User-Id"):
            try:
                uid = int(request.headers["X-User-Id"])
            except ValueError:
                raise exceptions.AuthenticationFailed("X-User-Id invalide.")
            role = request.headers.get("X-User-Role", "").lower()
            return AuthUser(id=uid, role=role), None
        return None

    def _from_token(self, token):
        try:
            payload = jwt.decode(
                token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM]
            )
        except jwt.ExpiredSignatureError:
            raise exceptions.AuthenticationFailed("Token expire.")
        except jwt.InvalidTokenError:
            raise exceptions.AuthenticationFailed("Token invalide.")
        try:
            uid = int(payload[settings.JWT_USER_ID_CLAIM])
            role = str(payload[settings.JWT_ROLE_CLAIM]).lower()
        except (KeyError, ValueError):
            raise exceptions.AuthenticationFailed("Claims du token incomplets.")
        return AuthUser(id=uid, role=role), token


class IsAuthenticatedRole(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)


class IsAdmin(IsAuthenticatedRole):
    def has_permission(self, request, view):
        return super().has_permission(request, view) and request.user.is_admin


class IsAdminOrReadOnly(IsAuthenticatedRole):
    """Structure academique : lecture pour tous, ecriture admin (UC-ADMIN-03)."""

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        return request.method in permissions.SAFE_METHODS or request.user.is_admin


class IsAdminOrSupervisor(IsAuthenticatedRole):
    def has_permission(self, request, view):
        return super().has_permission(request, view) and (
            request.user.is_admin or request.user.is_supervisor
        )


class IsAdminOrTeacher(IsAuthenticatedRole):
    def has_permission(self, request, view):
        return super().has_permission(request, view) and (
            request.user.is_admin or request.user.is_teacher
        )
