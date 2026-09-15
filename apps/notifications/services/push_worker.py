"""NOTIF-A : routage push stub (iOS alert/VoIP vs FCM). Jamais d'envoi réel en lab."""

from django.conf import settings

from apps.iam.models import Device
from apps.notifications.models import Notification

_CALL_TYPES = frozenset({Notification.Type.CALL_INCOMING, "CALL_CANCELLED"})


def channel_status(token: str, configured: bool) -> str:
    if not token:
        return "skipped_no_token"
    if not configured:
        return "not_configured"
    return "sent"  # jamais atteint tant qu'aucune clé FCM/APNs n'est configurée


def _channel_kind(platform: str, notif_type: str) -> str:
    if platform == Device.Platform.IOS:
        return "apns_voip" if notif_type in _CALL_TYPES else "apns_alert"
    return "fcm"


def send_push(device: Device, notif_type: str, title: str, body: str, payload: dict) -> dict:
    """Routage automatique pour emit(). data seul et priorité haute pour les appels : non
    simulés ici (stub), seul le choix du canal / jeton est modélisé."""
    kind = _channel_kind(device.platform, notif_type)
    token = device.voip_push_token if kind == "apns_voip" else device.push_token
    configured = (
        bool(settings.APNS_KEY_PATH) if kind.startswith("apns") else bool(settings.FCM_SERVER_KEY)
    )
    return {"channel": kind, "status": channel_status(token, configured)}


def send_test(device: Device, channel: str) -> list[dict]:
    """NOTIF-17 : diagnostic explicite, un jeton manquant ne bloque pas les autres canaux."""
    if device.platform != Device.Platform.IOS:
        configured = bool(settings.FCM_SERVER_KEY)
        return [{"channel": "fcm", "status": channel_status(device.push_token, configured)}]

    configured = bool(settings.APNS_KEY_PATH)
    results = []
    if channel in ("alert", "both"):
        results.append(
            {"channel": "apns_alert", "status": channel_status(device.push_token, configured)}
        )
    if channel in ("voip", "both"):
        results.append(
            {"channel": "apns_voip", "status": channel_status(device.voip_push_token, configured)}
        )
    return results
