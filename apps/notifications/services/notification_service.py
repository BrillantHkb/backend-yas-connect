"""NOTIF-A : emit() (moteur), inbox, préférences, DND (NOTIF-01…09, 16)."""

from datetime import timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.utils import timezone

from apps.iam.exceptions import AuthAPIError
from apps.notifications.models import Notification, NotificationPreference
from apps.notifications.services import push_worker

MSG_NOT_FOUND = "Notification introuvable."
MSG_VALIDATION = "Paramètre invalide."

_IDEMPOTENCY_WINDOW = timedelta(seconds=30)
_NO_INBOX_TYPES = frozenset({"CALL_CANCELLED", "PUSH_TEST"})
_PREFS_ALLOWED = frozenset(
    {
        "push_enabled", "in_app_enabled", "call_ring_enabled", "message_preview_enabled",
        "quiet_hours_enabled", "quiet_hours_start", "quiet_hours_end",
    }
)
_DEFAULT_TZ = "Africa/Lome"


def ensure_preferences(user) -> NotificationPreference:
    row, _ = NotificationPreference.objects.get_or_create(user=user)
    return row


def _in_quiet_hours(prefs: NotificationPreference) -> bool:
    if not prefs.quiet_hours_enabled or not prefs.quiet_hours_start or not prefs.quiet_hours_end:
        return False
    tz_name = getattr(getattr(prefs.user, "preferences", None), "timezone", None) or _DEFAULT_TZ
    try:
        tz = ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        tz = ZoneInfo(_DEFAULT_TZ)
    now_local = timezone.now().astimezone(tz).time()
    start, end = prefs.quiet_hours_start, prefs.quiet_hours_end
    if start <= end:
        return start <= now_local <= end
    return now_local >= start or now_local <= end  # fenêtre traversant minuit


def emit(
    *, user, type_, title, body="", payload=None, collapse_key="", ignore_dnd=False
) -> Notification | None:
    """Idempotent 30 s sur (user, type, collapse_key). Pas d'inbox pour CALL_CANCELLED/PUSH_TEST."""
    payload = payload or {}
    row = None
    if collapse_key:
        cutoff = timezone.now() - _IDEMPOTENCY_WINDOW
        row = (
            Notification.objects.filter(
                user=user, type=type_, collapse_key=collapse_key, created_at__gte=cutoff
            )
            .order_by("-created_at")
            .first()
        )
    if row is not None:
        row.title = title
        row.body = body
        row.payload = payload
        row.pushed_at = None
        row.save(update_fields=["title", "body", "payload", "pushed_at"])
    elif type_ not in _NO_INBOX_TYPES:
        row = Notification.objects.create(
            user=user, type=type_, title=title, body=body, payload=payload,
            collapse_key=collapse_key,
        )

    prefs = ensure_preferences(user)
    if not ignore_dnd and (not prefs.push_enabled or _in_quiet_hours(prefs)):
        return row

    sent = False
    for device in user.devices.exclude(push_token="", voip_push_token=""):
        result = push_worker.send_push(device, type_, title, body, payload)
        if result["status"] == "sent":
            sent = True
    if sent and row is not None:
        row.pushed_at = timezone.now()
        row.save(update_fields=["pushed_at"])
    return row


# --- NOTIF-01…04 : inbox ------------------------------------------------------


def _serialize(row: Notification) -> dict:
    return {
        "id": str(row.id),
        "type": row.type,
        "title": row.title,
        "body": row.body,
        "payload": row.payload,
        "read_at": row.read_at.isoformat() if row.read_at else None,
        "created_at": row.created_at.isoformat(),
    }


def list_inbox(*, user, before=None, limit=20, unread_only=False) -> dict:
    limit = min(max(int(limit or 20), 1), 50)
    qs = Notification.objects.filter(user=user)
    if unread_only:
        qs = qs.filter(read_at__isnull=True)
    if before:
        qs = qs.filter(created_at__lt=before)
    rows = list(qs.order_by("-created_at")[: limit + 1])
    next_before = None
    if len(rows) > limit:
        rows = rows[:limit]
        next_before = rows[-1].created_at.isoformat()
    return {"results": [_serialize(r) for r in rows], "next_before": next_before}


def unread_count(*, user) -> int:
    return Notification.objects.filter(user=user, read_at__isnull=True).count()


def mark_read(*, user, pk) -> None:
    try:
        row = Notification.objects.get(pk=pk, user=user)
    except Notification.DoesNotExist as exc:
        raise AuthAPIError(404, "NOT_FOUND", MSG_NOT_FOUND) from exc
    if row.read_at is None:
        row.read_at = timezone.now()
        row.save(update_fields=["read_at"])


def mark_all_read(*, user) -> None:
    Notification.objects.filter(user=user, read_at__isnull=True).update(read_at=timezone.now())


# --- NOTIF-05/06 : préférences -------------------------------------------------


def get_preferences(*, user) -> NotificationPreference:
    return ensure_preferences(user)


def serialize_preferences(row: NotificationPreference) -> dict:
    return {
        "push_enabled": row.push_enabled,
        "in_app_enabled": row.in_app_enabled,
        "call_ring_enabled": row.call_ring_enabled,
        "message_preview_enabled": row.message_preview_enabled,
        "quiet_hours_enabled": row.quiet_hours_enabled,
        "quiet_hours_start": row.quiet_hours_start.isoformat() if row.quiet_hours_start else None,
        "quiet_hours_end": row.quiet_hours_end.isoformat() if row.quiet_hours_end else None,
    }


def patch_preferences(*, user, data: dict) -> NotificationPreference:
    if not data:
        raise AuthAPIError(400, "VALIDATION_ERROR", "Aucun champ à modifier.")
    if set(data.keys()) - _PREFS_ALLOWED:
        raise AuthAPIError(400, "VALIDATION_ERROR", "Champ inconnu.")
    prefs = ensure_preferences(user)
    fields = []
    for key, value in data.items():
        setattr(prefs, key, value)
        fields.append(key)
    fields.append("updated_at")
    prefs.save(update_fields=fields)
    return prefs
