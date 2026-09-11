"""PROF-B : préférences UI + flag job_title_self_edit. Pas de privacy."""

import uuid
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from apps.iam.exceptions import AuthAPIError
from apps.iam.models import AuditLog, User, UserPreference

MSG_LANG = "Langue non supportée."
MSG_TZ = "Fuseau horaire invalide."
MSG_UNKNOWN = "Champ inconnu."
MSG_EMPTY = "Aucun champ à modifier."
MSG_BOOL = "Valeur booléenne invalide."

ALLOWED_LANGS = frozenset({"fr", "en"})
ALLOWED_KEYS = frozenset(
    {
        "language",
        "timezone",
        "notification_sound",
        "auto_download_media",
        "read_receipts",
        "typing_indicator",
    }
)
BOOL_KEYS = frozenset(
    {
        "notification_sound",
        "auto_download_media",
        "read_receipts",
        "typing_indicator",
    }
)


def job_title_self_edit() -> bool:
    """Politique globale. Défaut false si ligne absente. Pas de cache lab."""
    from apps.config.models import SystemSetting

    row = SystemSetting.objects.filter(
        category="profile", setting_key="job_title_self_edit"
    ).first()
    if row is None or row.setting_value is None:
        return False
    value = row.setting_value
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes"}
    return bool(value)


def _prefs_row(user: User) -> UserPreference:
    try:
        return user.preferences
    except UserPreference.DoesNotExist:
        prefs, _ = UserPreference.objects.get_or_create(user=user)
        return prefs


def serialize_preferences(user: User) -> dict:
    """GET /me/preferences et GET /me/onboarding (même JSON)."""
    prefs = _prefs_row(user)
    language = prefs.language or user.language or "fr"
    tz = prefs.timezone or user.timezone or "Africa/Lome"
    return {
        "language": language,
        "timezone": tz,
        "notification_sound": prefs.notification_sound,
        "auto_download_media": prefs.auto_download_media,
        "read_receipts": prefs.read_receipts,
        "typing_indicator": prefs.typing_indicator,
        "last_updated": prefs.last_updated.isoformat() if prefs.last_updated else None,
    }


def _validate_language(value) -> str:
    if not isinstance(value, str) or value.strip().lower() not in ALLOWED_LANGS:
        raise AuthAPIError(400, "INVALID_LANGUAGE", MSG_LANG)
    return value.strip().lower()


def _validate_timezone(value) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AuthAPIError(400, "INVALID_TIMEZONE", MSG_TZ)
    name = value.strip()
    try:
        ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise AuthAPIError(400, "INVALID_TIMEZONE", MSG_TZ) from exc
    return name


def _validate_bool(value, *, field: str) -> bool:
    if not isinstance(value, bool):
        raise AuthAPIError(400, "VALIDATION_ERROR", MSG_BOOL)
    return value


def apply_preference_updates(*, user: User, data: dict, actor=None, ip=None, audit=False) -> dict:
    """Écrit les clés présentes. Align users.language / timezone."""
    prefs = _prefs_row(user)
    old = {}
    new = {}
    user_fields = []

    if "language" in data:
        value = _validate_language(data["language"])
        old["language"] = prefs.language
        prefs.language = value
        user.language = value
        new["language"] = value
        user_fields.append("language")
    if "timezone" in data:
        value = _validate_timezone(data["timezone"])
        old["timezone"] = prefs.timezone
        prefs.timezone = value
        user.timezone = value
        new["timezone"] = value
        user_fields.append("timezone")
    for key in BOOL_KEYS:
        if key not in data:
            continue
        value = _validate_bool(data[key], field=key)
        old[key] = getattr(prefs, key)
        setattr(prefs, key, value)
        new[key] = value

    if user_fields:
        user.save(update_fields=[*user_fields, "updated_at"])
    prefs.save()
    if audit:
        AuditLog.objects.create(
            trace_id=uuid.uuid4(),
            module="IAM",
            action="PREFS_PATCH",
            entity_type="user_preferences",
            entity_id=prefs.id,
            old_values=old or None,
            new_values=new or None,
            ip_address=ip,
            severity="INFO",
            success=True,
            user=actor,
        )
    user.refresh_from_db()
    return serialize_preferences(user)


def patch_preferences(*, user: User, data, actor, ip) -> dict:
    if data is None:
        raise AuthAPIError(400, "VALIDATION_ERROR", MSG_EMPTY)
    raw_keys = set(data.keys())
    if not raw_keys:
        raise AuthAPIError(400, "VALIDATION_ERROR", MSG_EMPTY)
    if raw_keys - ALLOWED_KEYS:
        raise AuthAPIError(400, "UNKNOWN_FIELD", MSG_UNKNOWN)
    return apply_preference_updates(
        user=user, data=data, actor=actor, ip=ip, audit=True
    )
