"""HasPermission AUTH-R. IsAdminRole conservé mais inutilisé sur l’API."""

from rest_framework.permissions import BasePermission

from apps.iam.exceptions import AuthAPIError
from apps.iam.services.rbac_service import MSG_FORBIDDEN, user_has_permission


def resolve_required_permission(view, request) -> str | None:
    """required_permission (str) ou required_permissions {METHOD: code}."""
    code = getattr(view, "required_permission", None)
    if code:
        return code
    mapping = getattr(view, "required_permissions", None)
    if isinstance(mapping, dict):
        return mapping.get(request.method)
    return None


class HasPermission(BasePermission):
    """Fail-closed : attribut manquant ou code absent du rôle → 403 FORBIDDEN."""

    def has_permission(self, request, view):
        if request.method == "OPTIONS":
            return True
        user = request.user
        if user is None or not getattr(user, "is_authenticated", False):
            return False
        code = resolve_required_permission(view, request)
        if not code:
            raise AuthAPIError(403, "FORBIDDEN", MSG_FORBIDDEN, extra={"permission": None})
        if not user_has_permission(user, code):
            raise AuthAPIError(403, "FORBIDDEN", MSG_FORBIDDEN, extra={"permission": code})
        return True


class IsAdminRole(BasePermission):
    """JWT + role.code == ADMIN. Plus utilisé sur l’API (HasPermission)."""

    message = "Droits administrateur requis."

    def has_permission(self, request, view):
        user = request.user
        if user is None or not getattr(user, "is_authenticated", False):
            return False
        role = getattr(user, "role", None)
        return bool(role) and role.code == "ADMIN"
