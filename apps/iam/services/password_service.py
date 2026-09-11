"""AUTH-G : rotate / forgot / verify TOTP / reset. Uniquement le hash app."""

import secrets
import uuid
from datetime import timedelta

from django.utils import timezone

from apps.iam.exceptions import AuthAPIError
from apps.iam.helpers.hashers import verify_dummy  # réexport AUTH-A / AUTH-D
from apps.iam.models import (
    AuditLog,
    PasswordHistory,
    PasswordResetToken,
    ResetChannel,
    User,
)
from apps.iam.services import rate_limit_service
from apps.iam.services.mfa_service import consume_backup, mfa_ready, verify_totp
from apps.iam.services.password_policy import (
    enforce_password_policy,
    password_history_n,
    password_reset_ttl,
)
from apps.iam.services.token_service import hash_refresh_token

__all__ = [
    "MSG_FORGOT",
    "request_reset",
    "reset_password",
    "rotate_password",
    "set_password_with_history",
    "verify_dummy",
    "verify_password",
    "verify_reset_mfa",
]

MSG_OLD = "Ancien mot de passe incorrect."
MSG_SAME = "Le nouveau mot de passe doit être différent."
MSG_REUSED = "Ce mot de passe a déjà été utilisé."
MSG_MFA = "Code invalide."
MSG_TOKEN = "Jeton de réinitialisation invalide."
MSG_FORGOT = "Si un compte correspond, saisissez le code Google Authenticator."


def verify_password(password: str, encoded: str) -> bool:
    """True si le clair correspond au hash stocké (users.password_hash / colonne password)."""
    from django.contrib.auth.hashers import check_password

    return check_password(password, encoded)


def _audit(*, action: str, user=None, entity_id=None, metadata=None, ip=None, success=True):
    AuditLog.objects.create(
        trace_id=uuid.uuid4(),
        module="IAM",
        action=action,
        entity_type="users",
        entity_id=entity_id,
        metadata=metadata,
        ip_address=ip,
        severity="INFO",
        success=success,
        user=user,
    )


def _assert_not_reused(user: User, new_password: str) -> None:
    """Hash courant + N derniers password_history (AUTH-45)."""
    if verify_password(new_password, user.password):
        raise AuthAPIError(400, "PASSWORD_REUSED", MSG_REUSED)
    n = password_history_n()
    for row in user.password_history.order_by("-created_at")[:n]:
        if verify_password(new_password, row.password_hash):
            raise AuthAPIError(400, "PASSWORD_REUSED", MSG_REUSED)


def _archive_and_set(user: User, new_password: str) -> None:
    """Archive le hash courant, pose le nouveau, garde N lignes d’historique."""
    PasswordHistory.objects.create(user=user, password_hash=user.password)
    n = password_history_n()
    keep = list(
        PasswordHistory.objects.filter(user=user)
        .order_by("-created_at")
        .values_list("id", flat=True)[:n]
    )
    PasswordHistory.objects.filter(user=user).exclude(id__in=keep).delete()
    user.set_password(new_password)
    user.save(update_fields=["password", "updated_at"])


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _lookup(*, email, username) -> User | None:
    """Même lookup que AUTH-A, sans importer auth_service (cycle)."""
    from django.conf import settings

    qs = User.objects.select_related("otp_secret")
    try:
        if email:
            return qs.get(email=email)
        if not settings.YAS_LOGIN_ALLOW_USERNAME:
            return None
        return qs.get(username__iexact=username)
    except User.DoesNotExist:
        return None


def _user_resettable(user: User | None) -> bool:
    """Forgot no-op / verify dummy si pending, locked, disabled."""
    if user is None:
        return False
    if user.pending_approval or not user.is_active or user.is_locked:
        return False
    return True


def _revoke_unused_tickets(user: User) -> None:
    PasswordResetToken.objects.filter(
        user=user, used_at__isnull=True, revoked_at__isnull=True
    ).update(revoked_at=timezone.now())


def set_password_with_history(user: User, new_password: str) -> None:
    """Politique + history AUTH-G. Pas de logout (l’appelant révoque)."""
    enforce_password_policy(new_password, email=user.email, username=user.username)
    _assert_not_reused(user, new_password)
    _archive_and_set(user, new_password)


def rotate_password(
    *,
    user: User,
    old_password: str,
    new_password: str,
    logout_others: bool,
    current_session=None,
    ip=None,
) -> None:
    """AUTH-43 : ancien + nouveau. Jamais le MDP AD. logout_others (défaut true) saute la session courante."""
    if old_password == new_password:
        raise AuthAPIError(400, "SAME_PASSWORD", MSG_SAME)
    if not verify_password(old_password, user.password):
        raise AuthAPIError(400, "INVALID_OLD_PASSWORD", MSG_OLD)
    enforce_password_policy(new_password, email=user.email, username=user.username)
    _assert_not_reused(user, new_password)
    _archive_and_set(user, new_password)
    _audit(
        action="PASSWORD_CHANGE",
        user=user,
        entity_id=user.id,
        metadata={"logout_others": logout_others},
        ip=ip,
    )
    if logout_others:
        from apps.iam.services.auth_service import _force_logout_user

        except_id = current_session.id if current_session is not None else None
        _force_logout_user(
            user=user, reason="PASSWORD_CHANGE", except_session_id=except_id
        )


def request_reset(*, email, username, ip, user_agent: str) -> None:
    """AUTH-46/50 : toujours no-op côté client. Révoque tickets unused si user OK."""
    email = _normalize_email(email) if email else None
    username = username.strip() if username else None
    ident = email or username
    if rate_limit_service.is_forgot_limited(ident) or rate_limit_service.is_forgot_limited_ip(
        ip
    ):
        _audit(
            action="PASSWORD_FORGOT_RATE_LIMITED",
            metadata={"ident": ident},
            ip=ip,
            success=False,
        )
        return
    rate_limit_service.forgot_hit(ident, ip)
    user = _lookup(email=email, username=username)
    if not _user_resettable(user):
        return
    _revoke_unused_tickets(user)
    _audit(
        action="PASSWORD_FORGOT",
        user=user,
        entity_id=user.id,
        metadata={"channel": "TOTP"},
        ip=ip,
    )


def verify_reset_mfa(
    *,
    email,
    username,
    otp=None,
    backup_code=None,
    ip,
    user_agent: str = "",
) -> dict:
    """AUTH-47/48 : 400 MFA_INVALID unique. Ticket opaque, used_at NULL."""
    email = _normalize_email(email) if email else None
    username = username.strip() if username else None
    user = _lookup(email=email, username=username)
    dummy = True
    if _user_resettable(user) and mfa_ready(user):
        dummy = False
    ok = False
    if dummy:
        verify_dummy(otp or backup_code or "x")  # timing proche d’un check
    elif otp:
        ok = verify_totp(user, otp)
    elif backup_code:
        ok = consume_backup(user, backup_code)
    if dummy or not ok:
        raise AuthAPIError(400, "MFA_INVALID", MSG_MFA)
    now = timezone.now()
    _revoke_unused_tickets(user)
    raw = secrets.token_urlsafe(32)
    ttl = password_reset_ttl()
    PasswordResetToken.objects.create(
        user=user,
        token_hash=hash_refresh_token(raw),
        reset_channel=ResetChannel.TOTP,
        requested_ip=ip,
        user_agent=user_agent or "",
        expires_at=now + timedelta(seconds=ttl),
    )
    return {"reset_token": raw, "expires_in": ttl}


def reset_password(*, reset_token: str, new_password: str, logout_all: bool, ip=None) -> None:
    """AUTH-49 : ticket + nouveau hash. Pas de JWT. Ne déverrouille pas."""
    digest = hash_refresh_token(reset_token)
    now = timezone.now()
    ticket = (
        PasswordResetToken.objects.select_related("user")
        .filter(token_hash=digest)
        .first()
    )
    if (
        ticket is None
        or ticket.used_at is not None
        or ticket.revoked_at is not None
        or ticket.expires_at <= now
    ):
        raise AuthAPIError(400, "INVALID_TOKEN", MSG_TOKEN)
    user = ticket.user
    enforce_password_policy(new_password, email=user.email, username=user.username)
    _assert_not_reused(user, new_password)
    _archive_and_set(user, new_password)
    ticket.used_at = now
    ticket.save(update_fields=["used_at"])
    _audit(
        action="PASSWORD_RESET",
        user=user,
        entity_id=user.id,
        metadata={"logout_all": logout_all},
        ip=ip,
    )
    if logout_all:
        from apps.iam.services.auth_service import _force_logout_user

        _force_logout_user(user=user, reason="PASSWORD_RESET")
