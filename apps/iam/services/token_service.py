"""Access JWT (AUTH-09) + refresh opaque hashé (AUTH-10). Pas de SimpleJWT."""

import hashlib
import hmac
import secrets
from datetime import timedelta
from uuid import UUID

import jwt
from django.conf import settings
from django.utils import timezone

from apps.iam.models import RefreshToken, Session


def sign_access_token(*, user_id, email: str, role_id, role_code: str, jti: UUID) -> str:
    """Signe un JWT HS256. jti = sessions.access_jti (middleware / YasJWTAuthentication)."""
    now = timezone.now()
    payload = {
        "iss": settings.YAS_JWT_ISSUER,  # émetteur yas-connect
        "typ": "access",  # refuse un autre typ au decode
        "sub": str(user_id),  # users.id
        "email": email,
        "role_id": str(role_id),  # JWT / ACL plus tard
        "role": role_code,  # ex. USER
        "jti": str(jti),  # id unique du token = ligne session
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=settings.YAS_JWT_ACCESS_TTL_SECONDS)).timestamp()),  # 15 min
    }
    # JWT_TOKEN_SECRET ≠ DJANGO_SECRET_KEY (jour 0)
    return jwt.encode(payload, settings.JWT_TOKEN_SECRET, algorithm=settings.YAS_JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Vérifie signature, issuer, exp. Lève jwt.InvalidTokenError si faux / expiré."""
    return jwt.decode(
        token,
        settings.JWT_TOKEN_SECRET,
        algorithms=[settings.YAS_JWT_ALGORITHM],  # liste fermée : pas d’algo confusion
        issuer=settings.YAS_JWT_ISSUER,
        options={"require": ["exp", "iat", "jti", "sub", "iss", "typ"]},
    )


def hash_refresh_token(raw: str) -> str:
    """HMAC-SHA256 du refresh clair. Le clair n’est jamais stocké."""
    return hmac.new(
        settings.JWT_TOKEN_SECRET.encode(),
        raw.encode(),
        hashlib.sha256,
    ).hexdigest()


def issue_refresh(*, session: Session, user, ip) -> str:
    """INSERT refresh_tokens + copie le hash sur sessions.refresh_hash. Retourne le clair une fois."""
    raw = secrets.token_urlsafe(48)  # opaque, pas un JWT
    jti = session.refresh_jti  # déjà posé à la création / rotation de session
    now = timezone.now()
    refresh_exp = now + timedelta(seconds=settings.YAS_JWT_REFRESH_TTL_SECONDS)  # 7 j
    exp = min(refresh_exp, session.expires_at)  # AUTH-H : capé par le plafond session
    digest = hash_refresh_token(raw)
    RefreshToken.objects.create(
        session=session,
        user=user,
        token_hash=digest,  # jamais raw
        jti=jti,
        issued_at=now,
        expires_at=exp,
        created_ip=ip,
    )
    session.refresh_hash = digest
    session.save(update_fields=["refresh_hash", "updated_at"])
    return raw  # seul moment où le serveur connaît le clair
