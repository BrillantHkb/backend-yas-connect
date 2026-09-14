"""PROF-C : GET/PATCH /me/privacy. Masque collègue = profile_service (inchangé)."""

import uuid

from apps.iam.exceptions import AuthAPIError
from apps.iam.models import AuditLog, PrivacySetting, User, Visibility

MSG_UNKNOWN = "Champ inconnu."
MSG_EMPTY = "Aucun champ à modifier."
MSG_BOOL = "Valeur booléenne invalide."
MSG_VIS = "Visibilité invalide."
MSG_PREFS = "Utiliser /me/preferences pour ce champ."

VISIBILITY_KEYS = frozenset(
    {
        "last_seen_visibility",
        "profile_photo_visibility",
        "online_status_visibility",
    }
)
BOOL_KEYS = frozenset(
    {
        "read_receipts_enabled",
        "typing_indicator_enabled",
        "allow_calls",
        "allow_mentions",
        "allow_group_invites",
    }
)
ALLOWED_KEYS = VISIBILITY_KEYS | BOOL_KEYS
PREFS_KEYS = frozenset({"read_receipts", "typing_indicator"})
VISIBILITY_VALUES = frozenset(Visibility.values)


def _privacy_row(user: User) -> PrivacySetting:
    try:
        return user.privacy
    except PrivacySetting.DoesNotExist:
        row, _ = PrivacySetting.objects.get_or_create(user=user)
        return row


def serialize_privacy(user: User) -> dict:
    """GET /me/privacy : 8 champs + updated_at."""
    row = _privacy_row(user)
    return {
        "last_seen_visibility": row.last_seen_visibility,
        "profile_photo_visibility": row.profile_photo_visibility,
        "online_status_visibility": row.online_status_visibility,
        "read_receipts_enabled": row.read_receipts_enabled,
        "typing_indicator_enabled": row.typing_indicator_enabled,
        "allow_calls": row.allow_calls,
        "allow_mentions": row.allow_mentions,
        "allow_group_invites": row.allow_group_invites,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _validate_visibility(value) -> str:
    if not isinstance(value, str) or value not in VISIBILITY_VALUES:
        raise AuthAPIError(400, "INVALID_VISIBILITY", MSG_VIS)
    return value


def _validate_bool(value) -> bool:
    if not isinstance(value, bool):
        raise AuthAPIError(400, "VALIDATION_ERROR", MSG_BOOL)
    return value


def patch_privacy(*, user: User, data, actor, ip) -> dict:
    if data is None:
        raise AuthAPIError(400, "VALIDATION_ERROR", MSG_EMPTY)
    raw_keys = set(data.keys())
    if not raw_keys:
        raise AuthAPIError(400, "VALIDATION_ERROR", MSG_EMPTY)
    if raw_keys & PREFS_KEYS:
        raise AuthAPIError(400, "UNKNOWN_FIELD", MSG_PREFS)
    if raw_keys - ALLOWED_KEYS:
        raise AuthAPIError(400, "UNKNOWN_FIELD", MSG_UNKNOWN)

    row = _privacy_row(user)
    old = {}
    new = {}
    fields = ["updated_at"]

    for key in VISIBILITY_KEYS:
        if key not in data:
            continue
        value = _validate_visibility(data[key])
        old[key] = getattr(row, key)
        setattr(row, key, value)
        new[key] = value
        fields.append(key)
    for key in BOOL_KEYS:
        if key not in data:
            continue
        value = _validate_bool(data[key])
        old[key] = getattr(row, key)
        setattr(row, key, value)
        new[key] = value
        fields.append(key)

    row.save(update_fields=fields)
    AuditLog.objects.create(
        trace_id=uuid.uuid4(),
        module="IAM",
        action="PRIVACY_PATCH",
        entity_type="privacy_settings",
        entity_id=row.id,
        old_values=old or None,
        new_values=new or None,
        ip_address=ip,
        severity="INFO",
        success=True,
        user=actor,
    )
    user.refresh_from_db()
    return serialize_privacy(user)
