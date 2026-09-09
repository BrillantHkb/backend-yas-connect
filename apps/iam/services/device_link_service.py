"""AUTH-J : challenge QR 2ᵉ appareil. Cache seulement, 0 table. Pas de begin_mfa."""

from __future__ import annotations

import hmac
import secrets
import uuid
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from apps.iam.exceptions import AuthAPIError
from apps.iam.models import AuditLog, Device, LoginMethod, User
from apps.iam.services import rate_limit_service
from apps.iam.services.auth_service import MSG_INVALID, _history, complete_login
from apps.iam.services.mfa_service import _mfa_ready, _verify_totp, hash_mfa_token

LINK_PREFIX = "device-link:"
MSG_EXPIRED = "QR expiré. Réessayez."
MSG_FORBIDDEN = "Lien appareil refusé."
MSG_BACKUP = "Utiliser le code Authenticator, pas un code de secours."
MSG_SELF = "Scannez depuis un autre appareil."
MSG_TAKEN = "Cet appareil est déjà lié à un autre compte."
MSG_RATE = "Trop de tentatives. Réessayez plus tard."


def _key(challenge_id) -> str:
    return f"{LINK_PREFIX}{challenge_id}"


def _ttl() -> int:
    return int(settings.YAS_DEVICE_LINK_TTL_SECONDS)


def _expires_in(payload: dict) -> int:
    """Secondes restantes (LocMem n’expose pas TTL Redis)."""
    remaining = int(payload["expires_at"] - timezone.now().timestamp())
    return max(0, remaining)


def start_device_link(*, device_spec: dict, ip: str | None) -> dict:
    """AUTH-67 : challenge + QR. waiter_secret jamais dans le QR."""
    if rate_limit_service.is_device_link_limited(ip):
        raise AuthAPIError(429, "RATE_LIMITED", MSG_RATE)
    rate_limit_service.device_link_hit(ip)

    challenge_id = uuid.uuid4()
    waiter_secret = secrets.token_urlsafe(32)
    ttl = _ttl()
    now = timezone.now()
    cache.set(
        _key(challenge_id),
        {
            "status": "PENDING",
            "device_spec": device_spec,  # DeviceSpec du waiter (ordi)
            "waiter_secret_hash": hash_mfa_token(waiter_secret),
            "ip": ip,
            "user_id": None,
            "tokens": None,
            "expires_at": (now + timedelta(seconds=ttl)).timestamp(),
        },
        timeout=ttl,
    )
    return {
        "challenge_id": str(challenge_id),
        "waiter_secret": waiter_secret,  # une fois ; mémoire du waiter seulement
        "expires_in": ttl,
        "qr_payload": f"yasconnect://device-link/v1?cid={challenge_id}",
    }


def poll_device_link(*, challenge_id, waiter_secret: str | None) -> dict:
    """AUTH-68 : PENDING sans JWT. APPROVED = tokens one-shot puis cache supprimé."""
    if not waiter_secret:
        raise AuthAPIError(403, "DEVICE_LINK_FORBIDDEN", MSG_FORBIDDEN)
    key = _key(challenge_id)
    payload = cache.get(key)
    if payload is None:
        raise AuthAPIError(410, "DEVICE_LINK_EXPIRED", MSG_EXPIRED)
    if not hmac.compare_digest(payload["waiter_secret_hash"], hash_mfa_token(waiter_secret)):
        raise AuthAPIError(403, "DEVICE_LINK_FORBIDDEN", MSG_FORBIDDEN)
    if payload["status"] == "PENDING":
        return {"status": "PENDING", "expires_in": _expires_in(payload)}
    tokens = payload["tokens"]
    cache.delete(key)  # one-shot : 2e poll = 410
    return {"status": "APPROVED", **tokens}


def confirm_device_link(
    *,
    user: User,
    challenge_id,
    otp: str | None,
    backup_code: str | None,
    phone_device: Device | None,
    ip: str | None,
    user_agent: str,
) -> dict:
    """AUTH-69 : TOTP du téléphone. Pas de backup. JWT remis au waiter, pas ici."""
    if backup_code:
        raise AuthAPIError(400, "MFA_BACKUP_NOT_ALLOWED", MSG_BACKUP)
    if not otp:
        raise AuthAPIError(400, "VALIDATION_ERROR", "Fournir otp.")

    user = User.objects.select_related("otp_secret", "role", "preferences", "privacy").get(
        pk=user.pk
    )
    if not _mfa_ready(user):
        raise AuthAPIError(403, "MFA_NOT_ENROLLED", "MFA non configuré.")

    key = _key(challenge_id)
    payload = cache.get(key)
    if payload is None or payload["status"] != "PENDING":
        raise AuthAPIError(410, "DEVICE_LINK_EXPIRED", MSG_EXPIRED)

    spec = payload["device_spec"]
    if phone_device is not None and spec.get("device_uuid") == phone_device.device_uuid:
        raise AuthAPIError(400, "DEVICE_LINK_SELF", MSG_SELF)
    if Device.objects.filter(device_uuid=spec["device_uuid"]).exclude(user=user).exists():
        raise AuthAPIError(409, "DEVICE_UUID_TAKEN", MSG_TAKEN)

    # Même throttle AUTH-C (5 OTP) ; pas de lock compte AUTH-63
    if rate_limit_service.is_mfa_limited(user.id) or rate_limit_service.is_mfa_limited_ip(ip):
        _history(
            user=user,
            email=user.email,
            ip=ip,
            success=False,
            reason="RATE_LIMITED",
            user_agent=user_agent,
            login_method=LoginMethod.DEVICE_LINK,
        )
        raise AuthAPIError(401, "INVALID_CREDENTIALS", MSG_INVALID)
    rate_limit_service.mfa_hit(user.id, ip)

    if not _verify_totp(user, otp):
        _history(
            user=user,
            email=user.email,
            ip=ip,
            success=False,
            reason="MFA_INVALID",
            user_agent=user_agent,
            login_method=LoginMethod.DEVICE_LINK,
        )
        raise AuthAPIError(401, "INVALID_CREDENTIALS", MSG_INVALID)

    rate_limit_service.mfa_reset(user.id)
    tokens = complete_login(
        user=user,
        ip=ip,
        user_agent=user_agent,
        device_spec=spec,
        ident_key=user.email,
        login_method=LoginMethod.DEVICE_LINK,
    )
    device = Device.objects.get(user=user, device_uuid=spec["device_uuid"])
    payload["status"] = "APPROVED"
    payload["user_id"] = str(user.id)
    payload["tokens"] = tokens  # jamais dans l’audit
    cache.set(key, payload, timeout=max(1, _expires_in(payload)))
    AuditLog.objects.create(
        trace_id=uuid.uuid4(),
        module="IAM",
        action="DEVICE_LINK",
        entity_type="devices",
        entity_id=device.id,
        severity="INFO",
        success=True,
        user=user,
        ip_address=ip,
        metadata={"challenge_id": str(challenge_id), "platform": spec.get("platform")},
    )
    return {"linked": True, "device_id": str(device.id)}  # pas de JWT téléphone
