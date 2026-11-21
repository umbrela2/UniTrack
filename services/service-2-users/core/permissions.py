from rest_framework.permissions import SAFE_METHODS, BasePermission


def _role(request):
    return getattr(request.user, "role", None)


def _authenticated(request):
    return bool(request.user and request.user.is_authenticated)


class IsAdmin(BasePermission):
    """Administrateur (chef de département) uniquement."""

    def has_permission(self, request, view):
        return _authenticated(request) and _role(request) == "admin"


class IsAdminOrSupervisorReadOnly(BasePermission):
    """Admin : tout. Superviseur (doyen) : lecture seule. Autres : refusé (RG13/RG14)."""

    def has_permission(self, request, view):
        if not _authenticated(request):
            return False
        role = _role(request)
        if role == "admin":
            return True
        if role == "supervisor":
            return request.method in SAFE_METHODS
        return False
