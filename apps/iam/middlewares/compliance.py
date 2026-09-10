"""Portes AUTH-F : JWT OK mais métier 403 TOS puis ONBOARDING. JSON hors handler DRF."""

from django.http import JsonResponse

from apps.iam.middlewares.authentication import session_user_from_bearer
from apps.iam.services.compliance_service import (
    MSG_ONBOARDING_REQUIRED,
    MSG_TOS_REQUIRED,
    onboarding_ok,
    tos_ok,
)

# Préfixes publics : pas de Bearer requis (login, health, docs, QR waiter).
_PUBLIC_PREFIXES = (
    "/health",
    "/api/schema",
    "/api/docs",
    "/admin",
    "/api/v1/auth/login",
    "/api/v1/auth/refresh",
    "/api/v1/auth/mfa",
    "/api/v1/auth/register",
    "/api/v1/auth/device-link",
    "/api/v1/auth/password",  # AUTH-G forgot / verify / reset (public)
    "/api/v1/directory",
)


def _norm(path: str) -> str:
    """Sans slash final (sauf racine) pour égalité /me vs /me/ (APPEND_SLASH)."""
    if path != "/" and path.endswith("/"):
        return path.rstrip("/")
    return path


def _is_or_under(path: str, prefix: str) -> bool:
    """path == prefix ou path sous prefix/ (après normalisation)."""
    p = _norm(path)
    pre = _norm(prefix)
    return p == pre or p.startswith(pre + "/")


def _is_public(path: str) -> bool:
    return any(_is_or_under(path, p) for p in _PUBLIC_PREFIXES)


def _is_me_root(path: str) -> bool:
    """GET /api/v1/me seulement — ne pas ouvrir /me/devices."""
    return _norm(path) == "/api/v1/me"


def _is_tos(path: str) -> bool:
    return _is_or_under(path, "/api/v1/me/tos")


def _is_onboarding(path: str) -> bool:
    return _is_or_under(path, "/api/v1/me/onboarding")


def _is_heartbeat(request) -> bool:
    """PATCH /me/devices/current autorisé pendant les portes (session vivante)."""
    return request.method == "PATCH" and _norm(request.path) == "/api/v1/me/devices/current"


def _deny(code: str, message: str) -> JsonResponse:
    """Le handler DRF ne s’applique pas ici : JSON {success, code, message}."""
    return JsonResponse({"success": False, "code": code, "message": message}, status=403)


class ComplianceMiddleware:
    """Après AuthenticationMiddleware Django. Décode le Bearer comme YasJWTAuthentication."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if _is_public(request.path):
            return self.get_response(request)  # login / health / docs / waiter QR
        user = session_user_from_bearer(request)
        if user is None:
            return self.get_response(request)  # pas de JWT ou invalide → vue 401
        if _is_me_root(request.path) or _is_tos(request.path) or _is_heartbeat(request):
            return self.get_response(request)  # gates + accept CGU + heartbeat
        if not tos_ok(user):
            return _deny("TOS_REQUIRED", MSG_TOS_REQUIRED)
        if _is_onboarding(request.path):
            return self.get_response(request)  # wizard seulement après CGU
        if not onboarding_ok(user):
            return _deny("ONBOARDING_REQUIRED", MSG_ONBOARDING_REQUIRED)
        return self.get_response(request)
