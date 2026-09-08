"""Jour 3 : rôle ADMIN (is_staff). AUTH-R remplacera par HasPermission."""

from rest_framework.permissions import BasePermission


class IsAdminRole(BasePermission):
    """JWT + role.code == ADMIN. Pas de HasPermission ce jour."""

    message = "Droits administrateur requis."

    def has_permission(self, request, view):
        user = request.user
        if user is None or not getattr(user, "is_authenticated", False):
            return False
        role = getattr(user, "role", None)
        return bool(role) and role.code == "ADMIN"
