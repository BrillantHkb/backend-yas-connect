"""CRYPTO-A : upsert identity/SPK, OTPK batch/count, bundles, ensure_conversation_key."""

import base64
import os
import uuid

from django.utils import timezone

from apps.crypto.models import ConversationKey, IdentityKey, OneTimePreKey, SignedPreKey
from apps.crypto.services import wrapping
from apps.iam.exceptions import AuthAPIError
from apps.iam.models import Device, User

MSG_VALIDATION = "Paramètre invalide."
MSG_NOT_FOUND = "Utilisateur introuvable."
MSG_DEVICE_NOT_FOUND = "Appareil introuvable pour ce contact."
MSG_PEER_KEYS_MISSING = "Aucun appareil de ce contact n'a publié de clés."
MSG_CRYPTO_KEYS_MISSING = "Votre appareil n'a pas encore publié d'identité de chiffrement."
MSG_PEER_NOT_READY = "Ce contact n'a encore publié aucune clé de chiffrement."

_OTPK_BATCH_MAX = 100
_CONVERSATION_KEY_BYTES = 32


def _decode_b64(raw, field: str) -> bytes:
    if not isinstance(raw, str) or not raw:
        raise AuthAPIError(400, "VALIDATION_ERROR", MSG_VALIDATION, extra={"field": field})
    try:
        return base64.b64decode(raw, validate=True)
    except Exception as exc:
        raise AuthAPIError(400, "VALIDATION_ERROR", MSG_VALIDATION, extra={"field": field}) from exc


def _encode_b64(raw: bytes) -> str:
    return base64.b64encode(bytes(raw)).decode()


# --- CRY-01 : identité ---------------------------------------------------------


def upsert_identity(*, device: Device, registration_id, identity_public_key_b64: str) -> dict:
    if not isinstance(registration_id, int) or isinstance(registration_id, bool):
        raise AuthAPIError(
            400, "VALIDATION_ERROR", MSG_VALIDATION, extra={"field": "registration_id"}
        )
    key_bytes = _decode_b64(identity_public_key_b64, "identity_public_key")
    row, _ = IdentityKey.objects.update_or_create(
        device=device,
        defaults={
            "user": device.user,
            "registration_id": registration_id,
            "identity_public_key": key_bytes,
        },
    )
    return {
        "device_id": str(device.id),
        "registration_id": row.registration_id,
        "identity_public_key": _encode_b64(row.identity_public_key),
    }


# --- CRY-02 : signed prekey -----------------------------------------------------


def upsert_signed_prekey(
    *, device: Device, key_id, public_key_b64: str, signature_b64: str
) -> dict:
    if not isinstance(key_id, int) or isinstance(key_id, bool) or key_id < 0:
        raise AuthAPIError(400, "VALIDATION_ERROR", MSG_VALIDATION, extra={"field": "key_id"})
    public_key = _decode_b64(public_key_b64, "public_key")
    signature = _decode_b64(signature_b64, "signature")
    row, _ = SignedPreKey.objects.update_or_create(
        device=device,
        key_id=key_id,
        defaults={"public_key": public_key, "signature": signature},
    )
    return {
        "key_id": row.key_id,
        "public_key": _encode_b64(row.public_key),
        "signature": _encode_b64(row.signature),
    }


# --- CRY-03/04 : one-time prekeys -----------------------------------------------


def load_otpks(*, device: Device, keys: list) -> dict:
    if not isinstance(keys, list) or not keys:
        raise AuthAPIError(400, "VALIDATION_ERROR", MSG_VALIDATION, extra={"field": "keys"})
    if len(keys) > _OTPK_BATCH_MAX:
        raise AuthAPIError(400, "VALIDATION_ERROR", MSG_VALIDATION, extra={"field": "keys"})

    parsed = []
    for entry in keys:
        key_id = entry.get("key_id") if isinstance(entry, dict) else None
        public_key_b64 = entry.get("public_key") if isinstance(entry, dict) else None
        if not isinstance(key_id, int) or isinstance(key_id, bool) or key_id < 0:
            raise AuthAPIError(400, "VALIDATION_ERROR", MSG_VALIDATION, extra={"field": "key_id"})
        parsed.append((key_id, _decode_b64(public_key_b64, "public_key")))

    existing = set(
        OneTimePreKey.objects.filter(
            device=device, key_id__in=[k for k, _ in parsed]
        ).values_list("key_id", flat=True)
    )
    accepted = 0
    skipped = 0
    for key_id, public_key in parsed:
        if key_id in existing:
            skipped += 1
            continue
        OneTimePreKey.objects.create(device=device, key_id=key_id, public_key=public_key)
        existing.add(key_id)
        accepted += 1
    return {"accepted": accepted, "skipped": skipped}


def otpk_count(*, device: Device) -> int:
    return OneTimePreKey.objects.filter(device=device, consumed_at__isnull=True).count()


# --- CRY-05/06/14 : bundles ------------------------------------------------------


def get_target_user_or_404(user_id) -> User:
    try:
        return User.objects.get(pk=user_id)
    except (User.DoesNotExist, ValueError, TypeError) as exc:
        raise AuthAPIError(404, "NOT_FOUND", MSG_NOT_FOUND) from exc


def get_bundles(*, target_user: User, device_id=None) -> dict:
    """device_id (audit W37) : cible un seul appareil pour éviter de consommer un
    OTPK sur chaque appareil du contact quand le client n'a besoin que d'un seul
    (ex. device déjà connu d'une session précédente)."""
    devices = (
        Device.objects.filter(user=target_user, identity_key__isnull=False)
        .select_related("identity_key")
        .prefetch_related("signed_prekeys")
    )
    if device_id is not None:
        try:
            uuid.UUID(str(device_id))
        except (ValueError, TypeError, AttributeError) as exc:
            raise AuthAPIError(
                400, "VALIDATION_ERROR", MSG_VALIDATION, extra={"field": "device_id"}
            ) from exc
        devices = devices.filter(id=device_id)
        if not devices.exists():
            raise AuthAPIError(404, "NOT_FOUND", MSG_DEVICE_NOT_FOUND)
    bundles = []
    for device in devices:
        spk = device.signed_prekeys.order_by("-created_at").first()
        if spk is None:
            continue  # pas encore prêt pour X3DH (§0)
        otpk = (
            OneTimePreKey.objects.filter(device=device, consumed_at__isnull=True)
            .order_by("created_at")
            .first()
        )
        one_time_prekey = None
        if otpk is not None:
            otpk.consumed_at = timezone.now()
            otpk.save(update_fields=["consumed_at"])
            one_time_prekey = {"key_id": otpk.key_id, "public_key": _encode_b64(otpk.public_key)}
        bundles.append(
            {
                "device_id": str(device.id),
                "registration_id": device.identity_key.registration_id,
                "identity_public_key": _encode_b64(device.identity_key.identity_public_key),
                "signed_prekey": {
                    "key_id": spk.key_id,
                    "public_key": _encode_b64(spk.public_key),
                    "signature": _encode_b64(spk.signature),
                },
                "one_time_prekey": one_time_prekey,
            }
        )
    if not bundles:
        raise AuthAPIError(409, "PEER_KEYS_MISSING", MSG_PEER_KEYS_MISSING)
    return {"bundles": bundles}


# --- CRY-07 : garde sender (hook MESSAGERIE-B) ----------------------------------


def require_sender_identity(*, device: Device) -> None:
    if not IdentityKey.objects.filter(device=device).exists():
        raise AuthAPIError(409, "CRYPTO_KEYS_MISSING", MSG_CRYPTO_KEYS_MISSING)


# --- MESSAGERIE-B : garde destinataire (jour 25, non consommateur d'OTPK) -------


def require_peer_ready(*, target_user: User) -> None:
    """Existence seule (identity + au moins 1 SPK) — ne consomme jamais d'OTPK."""
    ready = Device.objects.filter(
        user=target_user, identity_key__isnull=False, signed_prekeys__isnull=False
    ).exists()
    if not ready:
        raise AuthAPIError(409, "PEER_KEYS_MISSING", MSG_PEER_NOT_READY)


# --- CRY-09 : clé de fil GROUP/AI (hook MESSAGERIE-C) ---------------------------


def ensure_conversation_key(conversation_id) -> ConversationKey:
    existing = ConversationKey.objects.filter(
        conversation_id=conversation_id, is_current=True
    ).first()
    if existing is not None:
        return existing
    raw_key = os.urandom(_CONVERSATION_KEY_BYTES)
    wrapped = wrapping.wrap(raw_key)
    return ConversationKey.objects.create(
        id=uuid.uuid4(),
        conversation_id=conversation_id,
        version=1,
        algorithm="AES-256-GCM",
        wrapped_key=wrapped,
        is_current=True,
    )


def group_content_key(conversation_id) -> bytes:
    """Clé brute (32o) d'un fil GROUP/AI, prête pour wrap_with_key/unwrap_with_key."""
    conv_key = ensure_conversation_key(conversation_id)
    return wrapping.unwrap(bytes(conv_key.wrapped_key))
