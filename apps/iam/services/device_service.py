"""Device upsert (AUTH-11) + 1 session active par appareil (AUTH-12)."""

from django.utils import timezone

from apps.iam.models import Device, Session


def upsert_device(*, user, spec: dict, ip) -> Device:
    """UK (user, device_uuid) : crée ou met à jour. Ne touche pas trusted / compromised / jailbreak."""
    now = timezone.now()
    device, _ = Device.objects.update_or_create(
        user=user,
        device_uuid=spec["device_uuid"],  # ID install client (localStorage web)
        defaults={
            "device_name": spec.get("device_name") or "",
            "model": spec.get("model") or "",
            "platform": spec["platform"],  # IOS / ANDROID / WEB / DESKTOP / OTHER
            "os_version": spec.get("os_version") or "",
            "app_version": spec.get("app_version") or "",
            "device_fingerprint": spec.get("device_fingerprint"),
            "push_token": spec.get("push_token") or "",  # FCM / APNs plus tard
            "ip_address": ip,
            "last_seen": now,
        },
    )
    return device


def revoke_active_sessions_for_device(*, device) -> None:
    """AUTH-12 : avant d’INSÉRER la nouvelle session, tue celles du même appareil."""
    now = timezone.now()
    Session.objects.filter(device=device, is_active=True).update(
        is_active=False,
        revoked_at=now,
        revoke_reason="NEW_LOGIN_SAME_DEVICE",
    )
