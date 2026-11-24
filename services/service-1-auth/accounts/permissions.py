
from rest_framework.permissions import BasePermission


class IsAdminRole(BasePermission):
    """
    Allow access only to users whose role is ADMIN.
    """

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role == "ADMIN"
        )


class HasCompletedPasswordChange(BasePermission):
    """
    Deny access while the user must change their temporary password.
    """

    message = "You must change your password before accessing this feature."

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and not request.user.must_change_password
        )
