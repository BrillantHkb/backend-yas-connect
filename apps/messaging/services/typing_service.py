"""MESSAGERIE-G : indicateurs de saisie. Dédup via cache, jamais un client Redis brut."""

from django.core.cache import cache

from apps.iam.models import PrivacySetting, UserPreference

_TTL_SECONDS = 5


def should_emit(user) -> bool:
    prefs, _ = UserPreference.objects.get_or_create(user=user)
    if not prefs.typing_indicator:
        return False
    privacy, _ = PrivacySetting.objects.get_or_create(user=user)
    return bool(privacy.typing_indicator_enabled)


def mark_typing_start(conversation_id, user_id) -> bool:
    """True si un nouvel événement doit être diffusé (dédup TTL 5 s, jamais pour typing.stop)."""
    key = f"typing:{conversation_id}:{user_id}"
    if cache.get(key):
        return False
    cache.set(key, True, timeout=_TTL_SECONDS)
    return True


def clear_typing(conversation_id, user_id) -> None:
    cache.delete(f"typing:{conversation_id}:{user_id}")
