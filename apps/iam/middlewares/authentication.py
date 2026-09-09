"""JWT Bearer : decode + session DB active + jti (AUTH-A / AUTH-09)."""

from uuid import UUID

import jwt
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from apps.iam.models import Session
from apps.iam.services.token_service import decode_access_token


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
        try:
            jti = UUID(str(payload["jti"]))
        except (KeyError, ValueError) as exc:
            raise AuthenticationFailed("Token invalide.") from exc
        try:
            # jti du JWT = sessions.access_jti (une session = un access)
            session = Session.objects.select_related("user", "user__role").get(access_jti=jti)
        except Session.DoesNotExist as exc:
            raise AuthenticationFailed("Session invalide.") from exc
        if not session.is_active:
            raise AuthenticationFailed("Session invalide.")  # logout / nouvel login même device
        request.yas_session = session  # pour AUTH-H plus tard (heartbeat, logout)
        return (session.user, payload)  # request.user = User IAM
