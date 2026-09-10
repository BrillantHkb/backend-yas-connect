"""AUTH-C : challenge MFA, TOTP Fernet, backups hashés. Jamais le secret / mfa_token en log."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid

import pyotp
from cryptography.fernet import Fernet
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from apps.iam.exceptions import AuthAPIError
from apps.iam.models import AuditLog, OtpSecret, User
from apps.iam.services import rate_limit_service

MSG_CHALLENGE = "Session MFA expirée. Reconnectez-vous."


def _fernet() -> Fernet:
    """Clé YAS_MFA_FERNET_KEY (.env), pas system_settings."""
    return Fernet(settings.YAS_MFA_FERNET_KEY.encode())


def encrypt_totp_secret(b32: str) -> bytes:
    """Secret Authenticator chiffré avant INSERT otp_secrets.secret."""
    return _fernet().encrypt(b32.encode())


def decrypt_totp_secret(blob: bytes) -> str:
    """bytes() : BinaryField peut renvoyer un memoryview."""
    return _fernet().decrypt(bytes(blob)).decode()


def hash_backup_code(raw: str) -> str:
    """Hash SHA-256 de XXXXXXXX (sans tiret). Le clair ne reste jamais en base."""
    normalized = raw.strip().upper().replace("-", "")
    return hashlib.sha256(normalized.encode()).hexdigest()


def generate_backup_codes(*, n: int) -> list[str]:
    """Affichage XXXX-XXXX. Stockage = hash de la forme sans tiret."""
    out = []
    for _ in range(n):
        raw = secrets.token_hex(4).upper()
        out.append(f"{raw[:4]}-{raw[4:]}")
    return out


def hash_mfa_token(raw: str) -> str:
    """HMAC du challenge : le clair n’est jamais la clé cache."""
    return hmac.new(
        settings.JWT_TOKEN_SECRET.encode(),
        raw.encode(),
        hashlib.sha256,
    ).hexdigest()


def mfa_ready(user: User) -> bool:
    """True seulement si enroll fini (enabled + verified_at). Seed = 0 ligne."""
    return _mfa_ready(user)


def verify_totp(user: User, otp: str) -> bool:
    """Preuve Authenticator (AUTH-C / AUTH-G)."""
    return _verify_totp(user, otp)


def consume_backup(user: User, raw: str) -> bool:
    """Consomme un code secours (AUTH-22 / AUTH-G)."""
    return _consume_backup(user, raw)


def _mfa_ready(user: User) -> bool:
    """True seulement si enroll fini (enabled + verified_at). Seed = 0 ligne."""
    try:
        otp = user.otp_secret
    except OtpSecret.DoesNotExist:
        return False
    return bool(otp.verified_at and otp.enabled)


def provision_qr(user: User) -> str:
    """Nouveau secret tant que verified_at is None (QR abandonné = rotate)."""
    b32 = pyotp.random_base32()
    OtpSecret.objects.update_or_create(
        user=user,
        defaults={
            "secret": encrypt_totp_secret(b32),
            "algorithm": "SHA1",
            "digits": 6,
            "period": 30,
            "issuer": settings.YAS_MFA_ISSUER,
            "backup_codes": [],
            "enabled": False,
            "verified_at": None,
        },
    )
    totp = pyotp.TOTP(b32, digits=6, interval=30)
    # otpauth:// totp Google Authenticator — pas le QR AUTH-J yasconnect://
    return totp.provisioning_uri(name=user.email, issuer_name=settings.YAS_MFA_ISSUER)


def begin_mfa(*, user, ip, user_agent, device_spec, ident_key, login_method) -> dict:
    """Après facteur 1 OK : pas de JWT, pas d’upsert device, pas de last_login."""
    raw = secrets.token_urlsafe(32)
    cache.set(
        f"mfa:challenge:{hash_mfa_token(raw)}",
        {
            "user_id": str(user.id),
            "login_method": str(login_method),  # PASSWORD ou LDAP pour complete_login
            "device_spec": device_spec,  # upsert device seulement après OTP OK
            "ip": ip,
            "user_agent": user_agent or "",
            "ident_key": ident_key,  # reset rate-limit login dans complete_login
        },
        timeout=settings.YAS_MFA_CHALLENGE_TTL_SECONDS,  # 5 min
    )
    enroll = not _mfa_ready(user)
    data = {
        "mfa_required": True,
        "mfa_token": raw,  # une fois au client ; jamais en login_history
        "enroll": enroll,
        "expires_in": settings.YAS_MFA_CHALLENGE_TTL_SECONDS,
    }
    if enroll:
        data["otpauth_uri"] = provision_qr(user)  # AUTH-19 : QR à scanner
    return data


def _verify_totp(user: User, otp: str) -> bool:
    """RFC 6238, fenêtre ±1 période (horloge téléphone)."""
    try:
        rec = user.otp_secret
    except OtpSecret.DoesNotExist:
        return False
    totp = pyotp.TOTP(
        decrypt_totp_secret(rec.secret),
        digits=rec.digits,
        interval=rec.period,
    )
    return bool(totp.verify(otp.strip(), valid_window=1))


def _consume_backup(user: User, raw: str) -> bool:
    """AUTH-22 : un hash consommé = irréversible. compare_digest anti-timing."""
    try:
        rec = user.otp_secret
    except OtpSecret.DoesNotExist:
        return False
    if not rec.backup_codes:
        return False
    digest = hash_backup_code(raw)
    hashes = list(rec.backup_codes)
    for i, stored in enumerate(hashes):
        if hmac.compare_digest(str(stored), digest):
            hashes.pop(i)
            rec.backup_codes = hashes
            rec.save(update_fields=["backup_codes", "updated_at"])
            return True
    return False


def verify_mfa(*, mfa_token: str, otp: str | None, backup_code: str | None, ip) -> dict:
    """AUTH-20/21/22 : seul chemin vers complete_login (JWT)."""
    from apps.iam.services.auth_service import MSG_INVALID, _history, complete_login

    key = f"mfa:challenge:{hash_mfa_token(mfa_token)}"
    payload = cache.get(key)
    if not payload:
        raise AuthAPIError(401, "MFA_CHALLENGE_EXPIRED", MSG_CHALLENGE)

    user = User.objects.select_related("otp_secret", "role", "preferences", "privacy").get(
        id=payload["user_id"]
    )
    # Même 401 AUTH-05 que MDP faux (pas 429 : pas d’énumération)
    if rate_limit_service.is_mfa_limited(user.id) or rate_limit_service.is_mfa_limited_ip(ip):
        _history(
            user=user,
            email=user.email,
            ip=ip,
            success=False,
            reason="RATE_LIMITED",
            user_agent=payload["user_agent"],
            login_method=payload["login_method"],
        )
        raise AuthAPIError(401, "INVALID_CREDENTIALS", MSG_INVALID)

    rate_limit_service.mfa_hit(user.id, ip)

    enroll = not _mfa_ready(user)
    if enroll and backup_code:
        raise AuthAPIError(400, "VALIDATION_ERROR", "Enroll : fournir otp, pas un code de secours.")

    ok = False
    if otp:
        ok = _verify_totp(user, otp)
    elif backup_code:
        ok = _consume_backup(user, backup_code)
    if not ok:
        _history(
            user=user,
            email=user.email,
            ip=ip,
            success=False,
            reason="MFA_INVALID",
            user_agent=payload["user_agent"],
            login_method=payload["login_method"],
        )
        raise AuthAPIError(401, "INVALID_CREDENTIALS", MSG_INVALID)

    extra = {}
    if enroll:
        codes = generate_backup_codes(n=settings.YAS_MFA_BACKUP_COUNT)
        rec = user.otp_secret
        rec.enabled = True
        rec.verified_at = timezone.now()  # AUTH-20 : enroll fini
        rec.backup_codes = [hash_backup_code(c) for c in codes]
        rec.save(update_fields=["enabled", "verified_at", "backup_codes", "updated_at"])
        extra["backup_codes"] = codes  # seul moment où le clair sort

    cache.delete(key)  # one-shot : le mfa_token ne se rejoue pas
    rate_limit_service.mfa_reset(user.id)
    tokens = complete_login(
        user=user,
        ip=payload["ip"],
        user_agent=payload["user_agent"],
        device_spec=payload["device_spec"],
        ident_key=payload["ident_key"],
        login_method=payload["login_method"],
    )
    tokens.update(extra)
    return tokens


def regenerate_backup_codes(*, user: User, otp: str) -> list[str]:
    """AUTH-23 : session déjà MFA. Anciens hashes remplacés d’un coup."""
    from apps.iam.services.auth_service import MSG_INVALID

    user = User.objects.select_related("otp_secret").get(pk=user.pk)
    if not _mfa_ready(user):
        raise AuthAPIError(403, "MFA_NOT_ENROLLED", "MFA non configuré.")
    if not _verify_totp(user, otp):
        raise AuthAPIError(401, "INVALID_CREDENTIALS", MSG_INVALID)
    codes = generate_backup_codes(n=settings.YAS_MFA_BACKUP_COUNT)
    rec = user.otp_secret
    rec.backup_codes = [hash_backup_code(c) for c in codes]
    rec.save(update_fields=["backup_codes", "updated_at"])
    AuditLog.objects.create(
        trace_id=uuid.uuid4(),
        module="IAM",
        action="MFA_BACKUP_REGEN",
        entity_type="users",
        entity_id=user.id,
        severity="INFO",
        success=True,
        user=user,
    )
    return codes  # une fois au client


def admin_reset_mfa(*, user_id, actor: User) -> None:
    """AUTH-24 : delete otp_secrets + kill sessions. Pas de DELETE /mfa user."""
    from apps.iam.services.auth_service import _force_logout_user

    try:
        target = User.objects.get(pk=user_id)
    except User.DoesNotExist as exc:
        raise AuthAPIError(404, "NOT_FOUND", "Utilisateur introuvable.") from exc
    OtpSecret.objects.filter(user=target).delete()
    _force_logout_user(user=target, reason="MFA_RESET")
    AuditLog.objects.create(
        trace_id=uuid.uuid4(),
        module="IAM",
        action="MFA_RESET",
        entity_type="users",
        entity_id=target.id,
        severity="WARNING",
        success=True,
        user=actor,
        metadata={"reason": "ADMIN_RESET"},
    )
