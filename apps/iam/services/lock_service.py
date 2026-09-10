"""AUTH-I : lock auto N échecs, lazy unlock, unlock admin / job, suspect pays."""

import uuid
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from apps.iam.models import AuditLog, LoginHistory, User
from apps.iam.services import rate_limit_service
from apps.iam.services.notify_stub import notify_suspicious_login


def _security_value(key: str, default):
    """Lit security.* si la ligne existe, sinon défaut (.env)."""
    from apps.config.models import SystemSetting

    row = SystemSetting.objects.filter(category="security", setting_key=key).first()
    if row is None or row.setting_value is None:
        return default
    return row.setting_value


def lock_after_failures() -> int:
    raw = _security_value("lock_after_failures", None)
    if raw is None:
        return settings.YAS_LOCK_AFTER_FAILURES
    return int(raw)


def lock_duration_seconds() -> int:
    raw = _security_value("lock_duration_seconds", None)
    if raw is None:
        return settings.YAS_LOCK_DURATION_SECONDS
    return int(raw)


def _reset_login_rate_limit(user: User) -> None:
    """Après unlock : l’ident ne doit plus être RATE_LIMITED (N lock = N AUTH-06)."""
    rate_limit_service.reset(user.email)
    if user.username:
        rate_limit_service.reset(user.username)


def _audit_lock(
    *,
    user: User,
    action: str,
    actor=None,
    ip=None,
    reason="",
    old_locked=None,
    old_at=None,
):
    metadata = {}
    if reason:
        metadata["reason"] = reason
    AuditLog.objects.create(
        trace_id=uuid.uuid4(),
        module="IAM",
        action=action,
        entity_type="users",
        entity_id=user.id,
        old_values={
            "is_locked": old_locked,
            "locked_at": old_at.isoformat() if old_at else None,
        },
        new_values={
            "is_locked": user.is_locked,
            "locked_at": user.locked_at.isoformat() if user.locked_at else None,
        },
        metadata=metadata or None,
        ip_address=ip,
        severity="WARNING" if action == "ACCOUNT_LOCK" else "INFO",
        success=True,
        user=actor,
    )


def maybe_lock_after_failure(user: User | None) -> None:
    """≥ N INVALID_CREDENTIALS depuis dernier succès / unlock → lock. 5e réponse reste 401."""
    if user is None or user.is_locked:
        return
    n = lock_after_failures()
    cutoff = None
    last_ok = (
        LoginHistory.objects.filter(user=user, success=True).order_by("-created_at").first()
    )
    if last_ok is not None:
        cutoff = last_ok.created_at
    last_unlock = (
        AuditLog.objects.filter(
            entity_type="users",
            entity_id=user.id,
            action__in=["ACCOUNT_UNLOCK", "ACCOUNT_UNLOCK_AUTO"],
        )
        .order_by("-created_at")
        .first()
    )
    if last_unlock is not None and (cutoff is None or last_unlock.created_at > cutoff):
        cutoff = last_unlock.created_at
    qs = LoginHistory.objects.filter(user=user, failure_reason="INVALID_CREDENTIALS")
    if cutoff is not None:
        qs = qs.filter(created_at__gt=cutoff)
    if qs.count() < n:
        return
    now = timezone.now()
    user.is_locked = True
    user.locked_at = now
    user.save(update_fields=["is_locked", "locked_at", "updated_at"])
    _audit_lock(user=user, action="ACCOUNT_LOCK", old_locked=False, old_at=None)


def _unlock(user: User, *, action: str, actor=None, ip=None, reason="") -> None:
    old_locked = user.is_locked
    old_at = user.locked_at
    user.is_locked = False
    user.locked_at = None
    user.save(update_fields=["is_locked", "locked_at", "updated_at"])
    _reset_login_rate_limit(user)
    _audit_lock(
        user=user,
        action=action,
        actor=actor,
        ip=ip,
        reason=reason,
        old_locked=old_locked,
        old_at=old_at,
    )


def lazy_unlock(user: User) -> None:
    """Après MDP/bind OK. locked_at NULL (fixture jour 1) → no-op."""
    if not user.is_locked or user.locked_at is None:
        return
    ttl = lock_duration_seconds()
    if user.locked_at + timedelta(seconds=ttl) > timezone.now():
        return
    _unlock(user, action="ACCOUNT_UNLOCK_AUTO")


def unlock_user(*, user: User, actor, ip=None, reason="") -> None:
    """Admin : 200 idempotent. Sessions inchangées."""
    _unlock(user, action="ACCOUNT_UNLOCK", actor=actor, ip=ip, reason=reason or "")


def unlock_expired() -> int:
    """Job account_unlock_reaper : locked_at + TTL ≤ now."""
    ttl = lock_duration_seconds()
    cutoff = timezone.now() - timedelta(seconds=ttl)
    qs = User.objects.filter(is_locked=True, locked_at__isnull=False, locked_at__lte=cutoff)
    count = 0
    for user in qs.iterator():
        _unlock(user, action="ACCOUNT_UNLOCK_AUTO")
        count += 1
    return count


def mark_suspicious(*, history: LoginHistory) -> None:
    """Nouveau pays vs dernier succès géolocalisé. 1er geo n’alerte pas. Login déjà réussi."""
    if not history.success or history.user_id is None or not history.country:
        return
    prev = (
        LoginHistory.objects.filter(user_id=history.user_id, success=True)
        .exclude(pk=history.pk)
        .exclude(country__isnull=True)
        .exclude(country="")
        .order_by("-created_at")
        .first()
    )
    if prev is None or prev.country == history.country:
        return
    if not history.suspicious:
        history.suspicious = True
        history.save(update_fields=["suspicious"])
    AuditLog.objects.create(
        trace_id=uuid.uuid4(),
        module="IAM",
        action="LOGIN_NEW_COUNTRY",
        entity_type="login_history",
        entity_id=history.id,
        metadata={"from": prev.country, "to": history.country},
        severity="WARNING",
        success=True,
        user=history.user,
        ip_address=history.ip_address,
    )
    notify_suspicious_login(user=history.user, history=history, previous_country=prev.country)
