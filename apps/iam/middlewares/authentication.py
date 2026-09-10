"""JWT Bearer : decode + session DB + JTI blacklist + idle / plafond AUTH-H."""

from uuid import UUID

import jwt
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from apps.iam.models import Session
from apps.iam.services.jti_blacklist import jti_blocked
from apps.iam.services.session_service import session_dead, touch_last_activity
from apps.iam.services.token_service import decode_access_token


def _session_from_access(payload):
    """Session si JTI OK et pas morte. None si idle / expirée / blacklist."""
    try:
        jti = UUID(str(payload["jti"]))
    except (KeyError, ValueError):
        return None
    if jti_blocked(jti):
        return None
    try:
        session = Session.objects.select_related("user", "user__role").get(access_jti=jti)
    except Session.DoesNotExist:
        return None
    if session_dead(session):
        return None
    return session


def session_user_from_bearer(request):
    """User IAM si Bearer access valide + session vivante. Sinon None (pas d’exception).

    DRF pose request.user dans la vue, pas dans Django MIDDLEWARE : le middleware
    CGU réutilise ce décodage. Token absent / invalide / expiré / idle → None (la vue 401).
    """
    header = request.META.get("HTTP_AUTHORIZATION") or ""
    if not header.startswith("Bearer "):
        return None
    raw = header[len("Bearer ") :].strip()
    if not raw:
        return None
    try:
        payload = decode_access_token(raw)  # signature + exp + iss
    except jwt.InvalidTokenError:
        return None
    if payload.get("typ") != "access":
        return None
    session = _session_from_access(payload)
    if session is None:
        return None
    return session.user


class YasJWTAuthentication(BaseAuthentication):
    """Branche DRF : Authorization: Bearer <jwt>. Login / refresh / health restent AllowAny."""

    keyword = "Bearer"

    def authenticate(self, request):
        header = request.META.get("HTTP_AUTHORIZATION") or ""
        if not header.startswith(f"{self.keyword} "):
            return None  # pas de header : anonyme (IsAuthenticated → 401 ailleurs)
        raw = header[len(self.keyword) + 1 :].strip()
        if not raw:
            return None
        try:
            payload = decode_access_token(raw)  # signature + exp + iss
        except jwt.ExpiredSignatureError as exc:
            raise AuthenticationFailed("Token expiré.") from exc
        except jwt.InvalidTokenError as exc:
            raise AuthenticationFailed("Token invalide.") from exc
        if payload.get("typ") != "access":
            raise AuthenticationFailed("Token invalide.")  # refuse un refresh déguisé
        session = _session_from_access(payload)
        if session is None:
            raise AuthenticationFailed("Session invalide.")
        request.yas_session = session
        touch_last_activity(session)
        return (session.user, payload)  # request.user = User IAM

    def authenticate_header(self, request):
        """DRF : sans ce header, AuthenticationFailed est coercé en 403."""
        return self.keyword
