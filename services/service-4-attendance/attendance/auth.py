"""Authentification JWT *locale* : S4 valide le token émis par S1 sans appeler S1
(clé partagée HS256 ou clé publique RS256, via variables d'environnement)."""
import jwt
from django.conf import settings
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import BasePermission

ADMIN, SUPERVISEUR, ENSEIGNANT, ETUDIANT = "ADMIN", "SUPERVISEUR", "ENSEIGNANT", "ETUDIANT"

ROLE_ALIASES = {
    "admin": ADMIN, "administrateur": ADMIN, "administrator": ADMIN,
    "superviseur": SUPERVISEUR, "supervisor": SUPERVISEUR,
    "enseignant": ENSEIGNANT, "teacher": ENSEIGNANT, "professeur": ENSEIGNANT,
    "etudiant": ETUDIANT, "étudiant": ETUDIANT, "student": ETUDIANT,
}


class AuthUser:
    is_authenticated = True
    is_anonymous = False

    def __init__(self, user_id, role, claims):
        self.id = str(user_id)
        self.pk = self.id
        self.role = role
        self.claims = claims
        self.email = claims.get("email", "")

    def __str__(self):
        return f"{self.role}:{self.id}"


def _normalize_role(claims):
    raw = claims.get(settings.JWT_ROLE_CLAIM) or claims.get("roles")
    if isinstance(raw, (list, tuple)):
        raw = raw[0] if raw else None
    if not raw:
        return None
    return ROLE_ALIASES.get(str(raw).strip().lower(), str(raw).strip().upper())


class JWTAuthentication(BaseAuthentication):
    def authenticate_header(self, request):
        return "Bearer"

    def authenticate(self, request):
        parts = get_authorization_header(request).split()
        if not parts or parts[0].lower() != b"bearer":
            return None
        if len(parts) != 2:
            raise AuthenticationFailed("En-tête Authorization invalide.")
        key = settings.JWT_PUBLIC_KEY if settings.JWT_ALGORITHM.startswith(("RS", "ES")) else settings.JWT_SECRET
        options = {"require": ["sub", "exp"]}
        kwargs = {}
        if settings.JWT_ISSUER:
            kwargs["issuer"] = settings.JWT_ISSUER
        if settings.JWT_AUDIENCE:
            kwargs["audience"] = settings.JWT_AUDIENCE
        else:
            options["verify_aud"] = False
        try:
            claims = jwt.decode(parts[1].decode(), key, algorithms=[settings.JWT_ALGORITHM], options=options, **kwargs)
        except jwt.ExpiredSignatureError:
            raise AuthenticationFailed("Token expiré.")
        except jwt.PyJWTError:
            raise AuthenticationFailed("Token invalide.")
        role = _normalize_role(claims)
        if role not in (ADMIN, SUPERVISEUR, ENSEIGNANT, ETUDIANT):
            raise AuthenticationFailed("Rôle absent ou inconnu dans le token.")
        return AuthUser(claims["sub"], role, claims), parts[1].decode()


def role_required(*roles):
    class _RolePermission(BasePermission):
        message = "Accès interdit pour votre rôle."

        def has_permission(self, request, view):
            return bool(request.user and getattr(request.user, "role", None) in roles)

    return _RolePermission
