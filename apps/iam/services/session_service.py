"""AUTH-H : idle / plafond, revoke partagé, liste, heartbeat. Pas d’import auth_service."""

import uuid
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from apps.iam.exceptions import AuthAPIError
from apps.iam.models import AuditLog, Device, RefreshToken, Session
from apps.iam.services.jti_blacklist import blacklist_jti

MSG_SESSION = "Session introuvable."
MSG_DEVICE = "Appareil introuvable."


def _security_value(key: str, default):
    """Lit security.* si la ligne existe, sinon défaut (.env)."""
    from apps.config.models import SystemSetting

    row = SystemSetting.objects.filter(category="security", setting_key=key).first()
    if row is None or row.setting_value is None:
        return default
    return row.setting_value


def session_idle_seconds() -> int:
    raw = _security_value("session_idle_seconds", None)
    if raw is None:
        return settings.YAS_SESSION_IDLE_SECONDS
    return int(raw)


def session_absolute_seconds() -> int:
    raw = _security_value("session_absolute_seconds", None)
    if raw is None:
        return settings.YAS_SESSION_ABSOLUTE_SECONDS
    return int(raw)


def session_heartbeat_min_seconds() -> int:
    raw = _security_value("session_heartbeat_min_seconds", None)
    if raw is None:
        return settings.YAS_SESSION_HEARTBEAT_MIN_SECONDS
    return int(raw)


def session_dead(session, now=None) -> str | None:
    """INACTIVE / EXPIRED / INACTIVITY, sinon None (session utilisable)."""
    now = now or timezone.now()
    if not session.is_active:
        return "INACTIVE"
    if session.expires_at <= now:
        return "EXPIRED"
    idle = session_idle_seconds()
    if session.last_activity + timedelta(seconds=idle) <= now:
        return "INACTIVITY"
    return None


def touch_last_activity(session, now=None) -> None:
    """Debounce heartbeat / JWT. Pas users.status."""
    now = now or timezone.now()
    min_interval = session_heartbeat_min_seconds()
    if session.last_activity + timedelta(seconds=min_interval) > now:
        return
    Session.objects.filter(pk=session.pk).update(last_activity=now, updated_at=now)
    session.last_activity = now


def kill_session_rows(sessions, *, reason: str, now=None) -> int:
    """Blacklist JTI puis is_active=false + refresh révoqués. sessions = iterable de Session."""
    now = now or timezone.now()
    rows = list(sessions)
    ids = [s.pk for s in rows]
    for s in rows:
        blacklist_jti(s.access_jti, ttl=settings.YAS_JWT_ACCESS_TTL_SECONDS)
    if not ids:
        return 0
    Session.objects.filter(pk__in=ids).update(
        is_active=False,
        revoked_at=now,
        revoke_reason=reason,
    )
    RefreshToken.objects.filter(session_id__in=ids, revoked_at__isnull=True).update(
        revoked_at=now,
        revoked_reason=reason,
    )
    return len(ids)


def revoke_sessions(*, user, reason: str, except_session_id=None) -> int:
    """Tue les sessions actives du user. AUTH-G except_session_id = courante à garder."""
    qs = Session.objects.filter(user=user, is_active=True)
    if except_session_id is not None:
        qs = qs.exclude(pk=except_session_id)
    return kill_session_rows(qs, reason=reason)


def _audit(*, action: str, user, entity_id=None, metadata=None):
    AuditLog.objects.create(
        trace_id=uuid.uuid4(),
        module="IAM",
        action=action,
        entity_type="sessions",
        entity_id=entity_id,
        metadata=metadata,
        severity="INFO",
        success=True,
        user=user,
    )


def logout_current(*, session: Session) -> None:
    """AUTH-53 : session courante seulement."""
    kill_session_rows([session], reason="LOGOUT")
    _audit(action="LOGOUT", user=session.user, entity_id=session.id)


def logout_all(*, user) -> None:
    """AUTH-55 : partout, y compris courant."""
    revoke_sessions(user=user, reason="LOGOUT_ALL")
    _audit(action="LOGOUT_ALL", user=user, entity_id=user.id)


def logout_session(*, user, session_id) -> None:
    """AUTH-54 : une session. 404 si autre user / inconnue (pas 403)."""
    try:
        session = Session.objects.get(pk=session_id, user=user, is_active=True)
    except Session.DoesNotExist as exc:
        raise AuthAPIError(404, "NOT_FOUND", MSG_SESSION) from exc
    kill_session_rows([session], reason="LOGOUT")
    _audit(
        action="LOGOUT",
        user=user,
        entity_id=session.id,
        metadata={"session_id": str(session.id)},
    )


def logout_device_sessions(*, user, device_id) -> None:
    """AUTH-54 : sessions de l’appareil. trusted / push_token inchangés. 404 autre user."""
    try:
        device = Device.objects.get(pk=device_id, user=user)
    except Device.DoesNotExist as exc:
        raise AuthAPIError(404, "NOT_FOUND", MSG_DEVICE) from exc
    qs = Session.objects.filter(user=user, device=device, is_active=True)
    kill_session_rows(qs, reason="LOGOUT")
    _audit(
        action="LOGOUT",
        user=user,
        entity_id=device.id,
        metadata={"device_id": str(device.id)},
    )


def list_sessions(*, user, current_session_id) -> list[dict]:
    """Actives et pas session_dead. Jamais hash / JTI."""
    now = timezone.now()
    rows = (
        Session.objects.filter(user=user, is_active=True)
        .select_related("device")
        .order_by("-login_at")
    )
    out = []
    for session in rows:
        if session_dead(session, now):
            continue
        device = session.device
        out.append(
            {
                "id": str(session.id),
                "device_id": str(device.id) if device is not None else None,
                "device_name": device.device_name if device is not None else "",
                "platform": device.platform if device is not None else None,
                "ip_address": session.ip_address,
                "login_at": session.login_at.isoformat() if session.login_at else None,
                "last_activity": session.last_activity.isoformat(),
                "login_method": session.login_method,
                "is_current": current_session_id is not None and session.id == current_session_id,
            }
        )
    return out


def heartbeat_current(*, session: Session) -> dict:
    """AUTH-60 : debounce 60 s. Renvoie last_activity en base (write ou no-op)."""
    touch_last_activity(session)
    session.refresh_from_db(fields=["last_activity"])
    return {"last_activity": session.last_activity.isoformat()}


def reap_sessions() -> int:
    """Job : INACTIVITY puis EXPIRED. Blacklist les JTI encore vivants."""
    now = timezone.now()
    idle_before = now - timedelta(seconds=session_idle_seconds())
    idle_rows = list(Session.objects.filter(is_active=True, last_activity__lte=idle_before))
    n = kill_session_rows(idle_rows, reason="INACTIVITY", now=now)
    exp_rows = list(Session.objects.filter(is_active=True, expires_at__lte=now))
    n += kill_session_rows(exp_rows, reason="EXPIRED", now=now)
    return n
