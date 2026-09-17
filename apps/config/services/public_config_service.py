"""Plafonds/fenêtres configurables, lus par les clients (audit W40).

Avant ce fichier, media.* était deja configurable via system_settings mais
jamais exposé ; messaging.* (fenêtre d'édition/suppression, max_members,
taille max d'un message) était en dur dans le code. Les deux vivent ici,
même lecture non cachée que `upload_service._max_bytes_for` (MEDIA-A).
"""

from apps.config.models import SystemSetting

_MEDIA_DEFAULTS = {
    "max_image_bytes": 10485760,
    "max_video_bytes": 16777216,
    "max_audio_bytes": 10485760,
    "max_document_bytes": 15728640,
    "max_other_bytes": 10485760,
    "max_video_duration_seconds": 90,
}
_MESSAGING_DEFAULTS = {
    "edit_window_minutes": 15,
    "delete_window_hours": 48,
    "max_members_default": 256,
    "max_encrypted_content_bytes": 65536,
}
_CLIENT_DEFAULTS = {
    "min_version": "",  # vide = mécanisme désactivé (W19)
}


def _category_dict(category: str, defaults: dict) -> dict:
    rows = {
        row.setting_key: row.setting_value
        for row in SystemSetting.objects.filter(category=category, setting_key__in=defaults)
    }
    return {key: rows.get(key, default) for key, default in defaults.items()}


def messaging_setting(key: str):
    """Une seule valeur messaging.* — évite de recharger toute la catégorie
    à chaque envoi/édition/suppression de message."""
    row = SystemSetting.objects.filter(category="messaging", setting_key=key).first()
    if row is None or row.setting_value is None:
        return _MESSAGING_DEFAULTS[key]
    return row.setting_value


def client_min_version() -> str:
    row = SystemSetting.objects.filter(category="client", setting_key="min_version").first()
    if row is None or not row.setting_value:
        return ""
    return str(row.setting_value)


def public_config() -> dict:
    return {
        "media": _category_dict("media", _MEDIA_DEFAULTS),
        "messaging": _category_dict("messaging", _MESSAGING_DEFAULTS),
        "client": _category_dict("client", _CLIENT_DEFAULTS),
    }
