"""Portes AUTH-F : après HasPermission (DRF). Middleware Django = pass-through."""

import re

from rest_framework.permissions import BasePermission

from apps.iam.exceptions import AuthAPIError
from apps.iam.services.compliance_service import (
    MSG_ONBOARDING_REQUIRED,
    MSG_TOS_REQUIRED,
    onboarding_ok,
    tos_ok,
)

_DEVICE_LOGOUT = re.compile(
    r"^/api/v1/me/devices/[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}/logout$"
)


def _norm(path: str) -> str:
    """Sans slash final (sauf racine) pour égalité /me vs /me/ (APPEND_SLASH)."""
    if path != "/" and path.endswith("/"):
        return path.rstrip("/")
    return path


def _is_or_under(path: str, prefix: str) -> bool:
    p = _norm(path)
    pre = _norm(prefix)
    return p == pre or p.startswith(pre + "/")


def _is_me_root_get(request) -> bool:
    """GET /me seulement (PATCH /me et avatar passent les portes AUTH-F)."""
    return request.method == "GET" and _norm(request.path) == "/api/v1/me"


def _is_tos(path: str) -> bool:
    return _is_or_under(path, "/api/v1/me/tos")


def _is_onboarding(path: str) -> bool:
    return _is_or_under(path, "/api/v1/me/onboarding")


def _is_heartbeat(request) -> bool:
    return request.method == "PATCH" and _norm(request.path) == "/api/v1/me/devices/current"


def _is_auth_logout(request) -> bool:
    return request.method == "POST" and _is_or_under(request.path, "/api/v1/auth/logout")


def _is_me_sessions(path: str) -> bool:
    return _is_or_under(path, "/api/v1/me/sessions")


def _is_device_logout(request) -> bool:
    return request.method == "POST" and bool(_DEVICE_LOGOUT.match(_norm(request.path)))


def _is_session_allowlist(request) -> bool:
    return (
        _is_auth_logout(request)
        or _is_me_sessions(request.path)
        or _is_device_logout(request)
    )


def _is_admin_api(path: str) -> bool:
    """ADMIN-A : JWT + HasPermission suffisent — pas de porte CGU/wizard."""
    return _is_or_under(path, "/api/v1/admin")


class ComplianceGates(BasePermission):
    """TOS / onboarding après HasPermission. Allowlist inchangée (AUTH-F / H)."""

    def has_permission(self, request, view):
        if request.method == "OPTIONS":
            return True
        user = request.user
        if user is None or not getattr(user, "is_authenticated", False):
            return True
        path = request.path
        if (
            _is_me_root_get(request)
            or _is_tos(path)
            or _is_heartbeat(request)
            or _is_session_allowlist(request)
            or _is_admin_api(path)
        ):
            return True
        if not tos_ok(user):
            raise AuthAPIError(403, "TOS_REQUIRED", MSG_TOS_REQUIRED)
        if _is_onboarding(path):
            return True
        if not onboarding_ok(user):
            raise AuthAPIError(403, "ONBOARDING_REQUIRED", MSG_ONBOARDING_REQUIRED)
        return True


class ComplianceMiddleware:
    """AUTH-R : les 403 CGU sont dans ComplianceGates (après HasPermission)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)
