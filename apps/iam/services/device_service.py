"""Device upsert (AUTH-11) + politique AUTH-E (27–36). Jamais DELETE devices."""

from __future__ import annotations

import uuid

from django.conf import settings
from django.utils import timezone

from apps.iam.exceptions import AuthAPIError
from apps.iam.models import AuditLog, Device, Session
from apps.iam.services.notify_stub import emit_device_new
from apps.iam.services.session_service import kill_session_rows

MSG_COMPROMISED = "Appareil signalé compromis."
MSG_JAILBROKEN = "Appareil non autorisé (root/jailbreak)."
MSG_NOT_FOUND = "Appareil introuvable."
MSG_CURRENT = "Utiliser revoke sur l’appareil courant."


def upsert_device(*, user, spec: dict, ip) -> tuple[Device, bool]:
    """UK (user, device_uuid). Ne touche pas trusted / compromised. Push seulement si fourni."""
    now = timezone.now()
    defaults = {
        "model": spec.get("model") or "",
        "platform": spec["platform"],  # IOS / ANDROID / WEB / DESKTOP / OTHER
        "os_version": spec.get("os_version") or "",
        "app_version": spec.get("app_version") or "",
        "device_fingerprint": spec.get("device_fingerprint"),
        "ip_address": ip,
        "last_seen": now,
        "jailbreak": bool(spec.get("jailbreak")),  # AUTH-32 : flag client
    }
    if spec.get("device_name"):
        defaults["device_name"] = spec["device_name"]  # ne pas écraser un rename AUTH-36
    if spec.get("push_token"):
        defaults["push_token"] = spec["push_token"]  # ne pas vider au relogin sans token
    device, created = Device.objects.update_or_create(
        user=user,
        device_uuid=spec["device_uuid"],  # ID install client (localStorage web)
        defaults=defaults,
    )
    return device, created


def revoke_active_sessions_for_device(*, device) -> None:
    """AUTH-12 : avant d’INSÉRER la nouvelle session, tue celles du même appareil."""
    qs = Session.objects.filter(device=device, is_active=True)
    kill_session_rows(qs, reason="NEW_LOGIN_SAME_DEVICE")


def jailbreak_blocked(*, device: Device) -> bool:
    """WEB/DESKTOP jamais bloqués. Mobile + flag + YAS_BLOCK_JAILBREAK."""
    if device.platform not in (Device.Platform.IOS, Device.Platform.ANDROID):
        return False
    if not device.jailbreak:
        return False
    return settings.YAS_BLOCK_JAILBREAK


def on_new_device(*, user, device, ip) -> None:
    """AUTH-29 : 1re vue (user, uuid). Audit + stub log. Pas de MFA extra."""
    AuditLog.objects.create(
        trace_id=uuid.uuid4(),
        module="IAM",
        action="DEVICE_NEW",
        entity_type="devices",
        entity_id=device.id,
        severity="WARNING",
        success=True,
        user=user,
        ip_address=ip,
        metadata={"device_uuid": device.device_uuid, "platform": device.platform},
    )
    emit_device_new(user=user, device=device)


def kill_device(*, device: Device, reason: str) -> None:
    """AUTH-33/34 : sessions + refresh + push vide + untrust. Ligne conservée."""
    qs = Session.objects.filter(device=device, is_active=True)
    kill_session_rows(qs, reason=reason)
    device.push_token = ""
    device.trusted = False
    if reason == "DEVICE_COMPROMISED":
        device.compromised = True
    device.save(update_fields=["push_token", "trusted", "compromised", "updated_at"])


def owned_device(*, user, device_id) -> Device:
    """404 si id d’un autre user (pas 403 : pas d’énumération)."""
    try:
        return Device.objects.get(pk=device_id, user=user)
    except Device.DoesNotExist as exc:
        raise AuthAPIError(404, "NOT_FOUND", MSG_NOT_FOUND) from exc


def get_device(*, device_id) -> Device:
    try:
        return Device.objects.get(pk=device_id)
    except Device.DoesNotExist as exc:
        raise AuthAPIError(404, "NOT_FOUND", MSG_NOT_FOUND) from exc


def set_trusted(*, user, device_id, trusted: bool) -> Device:
    """AUTH-30/31 : label UI. Pas de skip MFA. Sessions inchangées."""
    device = owned_device(user=user, device_id=device_id)
    if device.compromised and trusted:
        raise AuthAPIError(400, "DEVICE_COMPROMISED", MSG_COMPROMISED)
    device.trusted = trusted
    device.save(update_fields=["trusted", "updated_at"])
    return device


def rename_device(*, user, device_id, device_name: str) -> Device:
    """AUTH-36 : owner only."""
    device = owned_device(user=user, device_id=device_id)
    device.device_name = device_name
    device.save(update_fields=["device_name", "updated_at"])
    return device


def patch_owned_device(*, user, device_id, device_name=None, trusted=None) -> Device:
    device = owned_device(user=user, device_id=device_id)
    fields = ["updated_at"]
    if device_name is not None:
        device.device_name = device_name
        fields.append("device_name")
    if trusted is not None:
        if device.compromised and trusted:
            raise AuthAPIError(400, "DEVICE_COMPROMISED", MSG_COMPROMISED)
        device.trusted = trusted
        fields.append("trusted")
    device.save(update_fields=fields)
    return device


def patch_current_device(*, device: Device, spec: dict) -> Device:
    """Heartbeat session.current. 403 si compromis / jailbreak bloquant."""
    if device.compromised:
        raise AuthAPIError(403, "DEVICE_COMPROMISED", MSG_COMPROMISED)
    fields = ["updated_at", "last_seen"]
    device.last_seen = timezone.now()
    if "push_token" in spec and spec["push_token"] is not None:
        device.push_token = spec["push_token"]
        fields.append("push_token")
    if spec.get("app_version") is not None:
        device.app_version = spec["app_version"]
        fields.append("app_version")
    if spec.get("os_version") is not None:
        device.os_version = spec["os_version"]
        fields.append("os_version")
    if spec.get("jailbreak") is not None:
        device.jailbreak = bool(spec["jailbreak"])
        fields.append("jailbreak")
    device.save(update_fields=fields)
    if jailbreak_blocked(device=device):
        raise AuthAPIError(403, "DEVICE_JAILBROKEN", MSG_JAILBROKEN)
    return device


def revoke_device(*, user, device_id) -> Device:
    """AUTH-34 : déconnecter. Relogin même UUID OK."""
    device = owned_device(user=user, device_id=device_id)
    kill_device(device=device, reason="DEVICE_REVOKED")
    return device


def compromise_owned(*, user, device_id, current_device_id) -> Device:
    """AUTH-33 owner : interdit sur l’appareil de cette session."""
    device = owned_device(user=user, device_id=device_id)
    if current_device_id is not None and device.id == current_device_id:
        raise AuthAPIError(400, "CANNOT_COMPROMISE_CURRENT", MSG_CURRENT)
    kill_device(device=device, reason="DEVICE_COMPROMISED")
    return device


def compromise_admin(*, device_id) -> Device:
    """Admin : y compris l’appareil courant de la cible."""
    device = get_device(device_id=device_id)
    kill_device(device=device, reason="DEVICE_COMPROMISED")
    return device


def clear_compromise(*, device_id) -> Device:
    """Lève le ban. Ne réactive pas trusted."""
    device = get_device(device_id=device_id)
    device.compromised = False
    device.save(update_fields=["compromised", "updated_at"])
    return device


def serialize_device(device: Device, *, current_device_id) -> dict:
    """JSON liste : jamais push_token."""
    return {
        "id": str(device.id),
        "device_uuid": device.device_uuid,
        "device_name": device.device_name,
        "platform": device.platform,
        "model": device.model,
        "os_version": device.os_version,
        "app_version": device.app_version,
        "trusted": device.trusted,
        "compromised": device.compromised,
        "jailbreak": device.jailbreak,
        "last_seen": device.last_seen.isoformat() if device.last_seen else None,
        "ip_address": device.ip_address,
        "is_current": current_device_id is not None and device.id == current_device_id,
    }


def list_my_devices(*, user, current_device_id) -> list[dict]:
    rows = Device.objects.filter(user=user).order_by("-last_seen")
    return [serialize_device(d, current_device_id=current_device_id) for d in rows]
