"""
Vérification locale des JWT émis par S1 (Auth).
S2 ne fait que VÉRIFIER la signature (RS256 + clé publique) : elle n'émet rien.

Contrat de claims attendu (à confirmer avec S1) :
  sub            -> id (UUID) de l'utilisateur
  role           -> student | teacher | admin | supervisor
  department_id  -> optionnel
  exp            -> obligatoire
"""
import jwt
from django.conf import settings
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed

VALID_ROLES = {"student", "teacher", "admin", "supervisor"}
_public_key = None


def get_public_key():
    global _public_key
    if _public_key is None:
        try:
            _public_key = settings.JWT_PUBLIC_KEY_PATH.read_text()
        except FileNotFoundError:
            raise AuthenticationFailed("Clé publique JWT introuvable sur le serveur.")
    return _public_key


class TokenUser:
    """Utilisateur léger construit à partir du token (aucune requête en base)."""

    is_authenticated = True
    is_anonymous = False

    def __init__(self, payload):
        self.id = payload["sub"]
        self.role = payload["role"]
        self.department_id = payload.get("department_id")
        self.payload = payload

    def __str__(self):
        return f"{self.role}:{self.id}"


class JWTAuthentication(BaseAuthentication):
    def authenticate(self, request):
        parts = get_authorization_header(request).split()
        if not parts or parts[0].lower() != b"bearer":
            return None
        if len(parts) != 2:
            raise AuthenticationFailed("En-tête Authorization invalide.")
        try:
            payload = jwt.decode(
                parts[1].decode(),
                get_public_key(),
                algorithms=[settings.JWT_ALGORITHM],
                options={"require": ["exp", "sub"]},
            )
        except jwt.ExpiredSignatureError:
            raise AuthenticationFailed("Token expiré.")
        except jwt.InvalidTokenError:
            raise AuthenticationFailed("Token invalide.")
        if payload.get("role") not in VALID_ROLES:
            raise AuthenticationFailed("Rôle absent ou inconnu dans le token.")
        return (TokenUser(payload), payload)

    def authenticate_header(self, request):
        return "Bearer"


# Bouton "Authorize" dans Swagger
try:
    from drf_spectacular.extensions import OpenApiAuthenticationExtension

    class JWTScheme(OpenApiAuthenticationExtension):
        target_class = "core.jwt_verification.JWTAuthentication"
        name = "bearerAuth"

        def get_security_definition(self, auto_schema):
            return {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}
except ImportError:
    pass
