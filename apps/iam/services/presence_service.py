"""PRES-A : liveness cache, effective_status, PATCH, hooks appel. Login ≠ pastille."""

import uuid
from datetime import datetime, timezone as dt_timezone

from asgiref.sync import async_to_sync
from django.core.cache import cache
from django.db.models import Max
from django.utils import timezone

from apps.config.models import SystemSetting
from apps.iam.exceptions import AuthAPIError
from apps.iam.models import AuditLog, Session, User, Visibility
from apps.iam.services.session_service import touch_last_activity

MSG_EMPTY = "Aucun champ à modifier."
MSG_UNKNOWN = "Champ inconnu."
MSG_FIELD_UNKNOWN = "Champ inconnu."
MSG_VALIDATION = "Valeur invalide."
MSG_NOT_SETTABLE = "Ce statut n’est pas posable."
MSG_RESERVED = "Statut réservé (appels)."
MSG_UNKNOWN_STATUS = "Statut inconnu."
MSG_WATCH = "Trop d’utilisateurs à suivre."

ALLOWED_PATCH = frozenset({"status", "status_message"})
UNKNOWN_STATUSES = frozenset({"BUSY", "DND", "IN_FIELD"})
NOT_SETTABLE = frozenset({"AWAY", "OFFLINE"})

DEFAULT_TTL = 90
DEFAULT_AWAY = 300
WATCH_MAX = 100

LIVE_KEY = "presence:{}"
CONNS_KEY = "presence:conns:{}"


def _iso(dt):
    return dt.isoformat() if dt else None


def _int_setting(key: str, default: int) -> int:
    row = SystemSetting.objects.filter(category="presence", setting_key=key).first()
    if row is None or row.setting_value is None:
        return default
    try:
        return int(row.setting_value)
    except (TypeError, ValueError):
        return default


def redis_ttl_seconds() -> int:
    return _int_setting("redis_ttl_seconds", DEFAULT_TTL)


def away_after_seconds() -> int:
    return _int_setting("away_after_seconds", DEFAULT_AWAY)


def _live_key(user_id) -> str:
    return LIVE_KEY.format(user_id)


def _conns_key(user_id) -> str:
    return CONNS_KEY.format(user_id)


def _payload(user_id) -> dict | None:
    data = cache.get(_live_key(user_id))
    return data if isinstance(data, dict) else None


def _age_seconds(payload: dict, now=None) -> float:
    now = now or timezone.now()
    at = payload.get("at")
    if at is None:
        return 0.0
    try:
        at_dt = datetime.fromtimestamp(float(at), tz=dt_timezone.utc)
    except (TypeError, ValueError, OSError):
        return 0.0
    return max(0.0, (now - at_dt).total_seconds())


def connection_status(user: User, *, now=None) -> str:
    """Liveness seule : ONLINE / AWAY / OFFLINE. Ignore sticky PG."""
    payload = _payload(user.id)
    if not payload:
        return User.PresenceStatus.OFFLINE
    if _age_seconds(payload, now=now) > away_after_seconds():
        return User.PresenceStatus.AWAY
    return User.PresenceStatus.ONLINE


def effective_status(user: User, *, now=None) -> str:
    payload = _payload(user.id)
    if not payload:
        return User.PresenceStatus.OFFLINE
    if user.status == User.PresenceStatus.IN_MEETING:
        return User.PresenceStatus.IN_MEETING
    if _age_seconds(payload, now=now) > away_after_seconds():
        return User.PresenceStatus.AWAY
    return User.PresenceStatus.ONLINE


def badge_for(status: str | None) -> str | None:
    if status is None:
        return None
    return {
        User.PresenceStatus.ONLINE: "green",
        User.PresenceStatus.AWAY: "orange",
        User.PresenceStatus.IN_MEETING: "purple",
        User.PresenceStatus.OFFLINE: "grey",
    }.get(status)


def last_seen_at(user: User):
    """PRES-09 : max(presence.at, sessions.last_activity) sinon last_login."""
    candidates = []
    payload = _payload(user.id)
    if payload and payload.get("at") is not None:
        try:
            candidates.append(datetime.fromtimestamp(float(payload["at"]), tz=dt_timezone.utc))
        except (TypeError, ValueError, OSError):
            pass
    max_act = Session.objects.filter(user=user).aggregate(m=Max("last_activity"))["m"]
    if max_act is not None:
        candidates.append(max_act)
    if candidates:
        return max(candidates)
    return user.last_login


def show_online_status(*, viewer: User, target: User) -> bool:
    from apps.iam.services.profile_service import _visible

    privacy = getattr(target, "privacy", None)
    setting = privacy.online_status_visibility if privacy else Visibility.EVERYONE
    return _visible(setting, viewer, target)


def serialize_presence_self(user: User) -> dict:
    live = _payload(user.id) is not None
    conn = connection_status(user)
    availability = user.status
    status = effective_status(user) if live else User.PresenceStatus.OFFLINE
    return {
        "status": status,
        "connection": conn,
        "availability": availability,
        "badge": badge_for(status),
        "status_message": user.status_message or "",
        "last_seen": _iso(last_seen_at(user)),
        "last_login": _iso(user.last_login),
    }


def colleague_presence(*, target: User, viewer: User) -> dict:
    show = show_online_status(viewer=viewer, target=target)
    if not show:
        return {"status": None, "badge": None, "status_message": None}
    status = effective_status(target)
    return {
        "status": status,
        "badge": badge_for(status),
        "status_message": target.status_message or "",
    }


def ws_status_event(*, target: User, viewer: User) -> dict:
    show = show_online_status(viewer=viewer, target=target)
    body = {
        "type": "USER_STATUS_CHANGED",
        "user_id": str(target.id),
        "status": None,
        "badge": None,
    }
    if not show:
        return body
    status = effective_status(target)
    body["status"] = status
    body["badge"] = badge_for(status)
    body["status_message"] = target.status_message or ""
    return body


def set_live(user: User, *, device_id=None, notify: bool = True) -> datetime:
    now = timezone.now()
    cache.set(
        _live_key(user.id),
        {"at": now.timestamp(), "device_id": str(device_id) if device_id else None},
        timeout=redis_ttl_seconds(),
    )
    if notify:
        notify_watchers(user)
    return now


def clear_live(user: User, *, notify: bool = True) -> None:
    cache.delete(_live_key(user.id))
    if notify:
        notify_watchers(user)


def mark_socket_open(user: User, *, device_id=None) -> None:
    key = _conns_key(user.id)
    try:
        cache.incr(key)
    except ValueError:
        cache.set(key, 1, timeout=None)
    set_live(user, device_id=device_id, notify=False)
    sticky = user.status
    if sticky in (User.PresenceStatus.OFFLINE, User.PresenceStatus.AWAY):
        user.status = User.PresenceStatus.ONLINE
        user.save(update_fields=["status", "updated_at"])
    notify_watchers(user)


def mark_socket_close(user: User) -> None:
    key = _conns_key(user.id)
    try:
        left = cache.decr(key)
    except ValueError:
        left = 0
    if left <= 0:
        cache.delete(key)
        clear_live(user, notify=True)


def heartbeat(*, user: User, session=None, device_id=None) -> dict:
    now = set_live(user, device_id=device_id, notify=True)
    if session is not None:
        touch_last_activity(session, now=now)
    return {"at": now.isoformat()}


def notify_watchers(user: User) -> None:
    from channels.layers import get_channel_layer

    layer = get_channel_layer()
    if layer is None:
        return
    try:
        async_to_sync(layer.group_send)(
            f"presence.watch.{user.id}",
            {"type": "presence.notify", "user_id": str(user.id)},
        )
    except Exception:
        return


def patch_presence(*, user: User, data, actor, ip) -> dict:
    if data is None:
        raise AuthAPIError(400, "VALIDATION_ERROR", MSG_EMPTY)
    raw_keys = set(data.keys())
    if not raw_keys:
        raise AuthAPIError(400, "VALIDATION_ERROR", MSG_EMPTY)
    if "status_until" in raw_keys:
        raise AuthAPIError(400, "FIELD_UNKNOWN", MSG_FIELD_UNKNOWN)
    if raw_keys - ALLOWED_PATCH:
        raise AuthAPIError(400, "UNKNOWN_FIELD", MSG_UNKNOWN)
    if not (raw_keys & ALLOWED_PATCH):
        raise AuthAPIError(400, "VALIDATION_ERROR", MSG_EMPTY)

    old = {}
    new = {}
    update = []

    if "status" in data:
        value = data.get("status")
        if not isinstance(value, str):
            raise AuthAPIError(400, "VALIDATION_ERROR", MSG_VALIDATION)
        value = value.strip().upper()
        if value in UNKNOWN_STATUSES:
            raise AuthAPIError(400, "STATUS_UNKNOWN", MSG_UNKNOWN_STATUS)
        if value in NOT_SETTABLE:
            raise AuthAPIError(400, "STATUS_NOT_SETTABLE", MSG_NOT_SETTABLE)
        if value == User.PresenceStatus.IN_MEETING:
            raise AuthAPIError(400, "STATUS_RESERVED", MSG_RESERVED)
        if value != User.PresenceStatus.ONLINE:
            raise AuthAPIError(400, "STATUS_UNKNOWN", MSG_UNKNOWN_STATUS)
        old["status"] = user.status
        user.status = User.PresenceStatus.ONLINE
        new["status"] = user.status
        update.append("status")

    if "status_message" in data:
        value = data.get("status_message")
        if value is None:
            value = ""
        if not isinstance(value, str):
            raise AuthAPIError(400, "VALIDATION_ERROR", MSG_VALIDATION)
        value = value.strip()
        if len(value) > 140:
            raise AuthAPIError(400, "VALIDATION_ERROR", MSG_VALIDATION)
        old["status_message"] = user.status_message
        user.status_message = value
        new["status_message"] = value
        update.append("status_message")

    if not update:
        raise AuthAPIError(400, "VALIDATION_ERROR", MSG_EMPTY)

    update.append("updated_at")
    user.save(update_fields=update)
    AuditLog.objects.create(
        trace_id=uuid.uuid4(),
        module="IAM",
        action="PRESENCE_SET",
        entity_type="users",
        entity_id=user.id,
        old_values=old or None,
        new_values=new or None,
        ip_address=ip,
        severity="INFO",
        success=True,
        user=actor,
    )
    notify_watchers(user)
    return serialize_presence_self(user)


def on_call_started(user: User) -> None:
    user.status = User.PresenceStatus.IN_MEETING
    user.save(update_fields=["status", "updated_at"])
    notify_watchers(user)


def on_call_ended(user: User) -> None:
    user.status = User.PresenceStatus.ONLINE
    user.save(update_fields=["status", "updated_at"])
    notify_watchers(user)


def parse_watch_ids(raw) -> list:
    if not isinstance(raw, list):
        raise AuthAPIError(400, "VALIDATION_ERROR", MSG_VALIDATION)
    if len(raw) > WATCH_MAX:
        raise AuthAPIError(400, "VALIDATION_ERROR", MSG_WATCH)
    out = []
    for item in raw:
        try:
            out.append(str(uuid.UUID(str(item))))
        except (ValueError, TypeError, AttributeError) as exc:
            raise AuthAPIError(400, "VALIDATION_ERROR", MSG_VALIDATION) from exc
    return out
