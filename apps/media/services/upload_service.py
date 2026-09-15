"""MEDIA-A : upload générique (presign + multipart direct), quota, dédup, ACL owner-only."""

import hashlib
import re
import uuid
from pathlib import Path

from django.conf import settings

from apps.config.models import SystemSetting
from apps.iam.exceptions import AuthAPIError
from apps.iam.models import AuditLog, User
from apps.media.models import MediaAccessLog, MediaFile, StorageUsage
from apps.media.services import storage

MSG_VALIDATION = "Paramètre invalide."
MSG_FILE_TOO_LARGE = "Fichier trop volumineux."
MSG_QUOTA_EXCEEDED = "Quota de stockage dépassé."
MSG_UPLOAD_INCOMPLETE = "Fichier non trouvé dans le stockage (PUT non effectué)."
MSG_DUPLICATE_FILE = "Ce fichier existe déjà (checksum déjà utilisé)."
MSG_ALREADY_COMPLETED = "Upload déjà finalisé."
MSG_NOT_FOUND = "Fichier introuvable."
MSG_INFECTED = "Fichier rejeté par l’analyse antivirus."

_MULTIPART_MAX_BYTES = 10 * 1024 * 1024
_CHECKSUM_RX = re.compile(r"^[0-9a-fA-F]{64}$")
_DEFAULT_MAX_BYTES = {
    MediaFile.MediaType.IMAGE: 10485760,
    MediaFile.MediaType.AUDIO: 10485760,
    MediaFile.MediaType.DOCUMENT: 15728640,
    MediaFile.MediaType.OTHER: 10485760,
    MediaFile.MediaType.VIDEO: 16777216,
}


def _max_bytes_for(media_type: str) -> int:
    key = f"max_{media_type.lower()}_bytes"
    row = SystemSetting.objects.filter(category="media", setting_key=key).first()
    if row is None or row.setting_value is None:
        return _DEFAULT_MAX_BYTES.get(media_type, 10485760)
    try:
        return int(row.setting_value)
    except (TypeError, ValueError):
        return _DEFAULT_MAX_BYTES.get(media_type, 10485760)


def _infer_media_type(content_type: str) -> str:
    ct = (content_type or "").lower()
    if ct.startswith("image/"):
        return MediaFile.MediaType.IMAGE
    if ct.startswith("video/"):
        return MediaFile.MediaType.VIDEO
    if ct.startswith("audio/"):
        return MediaFile.MediaType.AUDIO
    if ct == "application/pdf" or "document" in ct or ct.startswith("text/"):
        return MediaFile.MediaType.DOCUMENT
    return MediaFile.MediaType.OTHER


def _normalize_checksum(raw) -> str:
    if not isinstance(raw, str) or not _CHECKSUM_RX.match(raw):
        raise AuthAPIError(400, "VALIDATION_ERROR", MSG_VALIDATION, extra={"field": "checksum"})
    return raw.lower()


def _quota_row(user: User) -> StorageUsage:
    row, _ = StorageUsage.objects.get_or_create(
        user=user, storage_type=StorageUsage.StorageType.PERSONAL, defaults={"used_bytes": 0}
    )
    return row


def _check_quota(user: User, size_bytes: int) -> None:
    row = _quota_row(user)
    if row.quota_bytes is not None and row.used_bytes + size_bytes > row.quota_bytes:
        raise AuthAPIError(413, "QUOTA_EXCEEDED", MSG_QUOTA_EXCEEDED)


def _apply_quota_delta(user: User, delta_bytes: int) -> None:
    row = _quota_row(user)
    row.used_bytes = max(0, row.used_bytes + delta_bytes)
    row.save(update_fields=["used_bytes", "updated_at"])


def _audit(*, action, actor, entity_id, old=None, new=None, ip=None):
    AuditLog.objects.create(
        trace_id=uuid.uuid4(),
        module="MEDIA",
        action=action,
        entity_type="media_files",
        entity_id=entity_id,
        old_values=old,
        new_values=new,
        ip_address=ip,
        severity="INFO",
        success=True,
        user=actor,
    )


def serialize_media(media: MediaFile) -> dict:
    return {
        "id": str(media.id),
        "original_name": media.original_name,
        "mime_type": media.mime_type,
        "media_type": media.media_type,
        "size_bytes": media.size_bytes,
        "checksum": media.checksum,
        "scan_status": media.scan_status,
        "encrypted": media.encrypted,
        "created_at": media.created_at.isoformat() if media.created_at else None,
    }


def get_own_media_or_404(user: User, pk) -> MediaFile:
    try:
        return MediaFile.objects.get(pk=pk, owner=user)
    except MediaFile.DoesNotExist as exc:
        raise AuthAPIError(404, "NOT_FOUND", MSG_NOT_FOUND) from exc


# --- MED-01 : init presign ----------------------------------------------------


def init_presigned_upload(*, user: User, data, actor, ip) -> dict:
    filename = (data.get("filename") or "").strip()
    mime_type = (data.get("mime_type") or "").strip()
    size_bytes = data.get("size_bytes")
    media_type = data.get("media_type")

    if media_type not in MediaFile.MediaType.values:
        raise AuthAPIError(400, "VALIDATION_ERROR", MSG_VALIDATION, extra={"field": "media_type"})
    if not isinstance(size_bytes, int) or isinstance(size_bytes, bool) or size_bytes <= 0:
        raise AuthAPIError(400, "VALIDATION_ERROR", MSG_VALIDATION, extra={"field": "size_bytes"})

    max_bytes = _max_bytes_for(media_type)
    if size_bytes > max_bytes:
        raise AuthAPIError(413, "FILE_TOO_LARGE", MSG_FILE_TOO_LARGE)
    _check_quota(user, size_bytes)

    ext = Path(filename).suffix[:20] if filename else ""
    key = storage.build_key(media_type, ext)
    media = MediaFile.objects.create(
        owner=user,
        storage_path=key,
        original_name=filename[:255],
        mime_type=mime_type[:100],
        media_type=media_type,
        size_bytes=size_bytes,
        bucket_name=settings.MINIO_BUCKET,
        scan_status=MediaFile.ScanStatus.PENDING,
    )
    url = storage.presigned_put_url(key, mime_type or "application/octet-stream")
    _audit(
        action="MEDIA_UPLOAD_INIT", actor=actor, entity_id=media.id,
        new=serialize_media(media), ip=ip,
    )
    return {"upload_id": str(media.id), "presigned_url": url, "expires_in": 900}


def complete_upload(*, user: User, upload_id, checksum, actor, ip) -> dict:
    try:
        media = MediaFile.objects.get(pk=upload_id, owner=user)
    except (MediaFile.DoesNotExist, ValueError, TypeError) as exc:
        raise AuthAPIError(404, "NOT_FOUND", MSG_NOT_FOUND) from exc
    if media.checksum:
        raise AuthAPIError(409, "ALREADY_COMPLETED", MSG_ALREADY_COMPLETED)

    checksum = _normalize_checksum(checksum)

    head = storage.head_object(media.storage_path)
    if head is None:
        raise AuthAPIError(400, "UPLOAD_INCOMPLETE", MSG_UPLOAD_INCOMPLETE)

    real_size = int(head.get("ContentLength") or 0)
    max_bytes = _max_bytes_for(media.media_type)
    if real_size > max_bytes:
        storage.delete_object(media.storage_path)
        media.delete()
        raise AuthAPIError(413, "FILE_TOO_LARGE", MSG_FILE_TOO_LARGE)

    if MediaFile.objects.filter(checksum=checksum).exclude(pk=media.pk).exists():
        raise AuthAPIError(409, "DUPLICATE_FILE", MSG_DUPLICATE_FILE)

    scan_status = (
        MediaFile.ScanStatus.SKIPPED
        if settings.YAS_MEDIA_SCAN_SKIP
        else MediaFile.ScanStatus.PENDING
    )
    media.checksum = checksum
    media.size_bytes = real_size
    media.scan_status = scan_status
    media.save(update_fields=["checksum", "size_bytes", "scan_status", "updated_at"])
    _apply_quota_delta(user, real_size)
    _audit(
        action="MEDIA_UPLOAD_COMPLETE", actor=actor, entity_id=media.id,
        new=serialize_media(media), ip=ip,
    )
    return serialize_media(media)


# --- MED-01 : multipart direct -------------------------------------------------


def direct_upload(*, user: User, uploaded, media_type_hint, actor, ip) -> dict:
    content_type = (getattr(uploaded, "content_type", None) or "").split(";")[0].strip().lower()
    media_type = (
        media_type_hint if media_type_hint in MediaFile.MediaType.values
        else _infer_media_type(content_type)
    )
    max_bytes = min(_MULTIPART_MAX_BYTES, _max_bytes_for(media_type))

    size = int(getattr(uploaded, "size", 0) or 0)
    if size > max_bytes:
        raise AuthAPIError(413, "FILE_TOO_LARGE", MSG_FILE_TOO_LARGE)
    data = uploaded.read()
    if len(data) > max_bytes:
        raise AuthAPIError(413, "FILE_TOO_LARGE", MSG_FILE_TOO_LARGE)
    _check_quota(user, len(data))

    checksum = hashlib.sha256(data).hexdigest()
    if MediaFile.objects.filter(checksum=checksum).exists():
        raise AuthAPIError(409, "DUPLICATE_FILE", MSG_DUPLICATE_FILE)

    ext = Path(getattr(uploaded, "name", "") or "").suffix[:20]
    key = storage.build_key(media_type, ext)
    storage.put_object_bytes(key, data, content_type or "application/octet-stream")

    scan_status = (
        MediaFile.ScanStatus.SKIPPED
        if settings.YAS_MEDIA_SCAN_SKIP
        else MediaFile.ScanStatus.PENDING
    )
    media = MediaFile.objects.create(
        owner=user,
        storage_path=key,
        original_name=(getattr(uploaded, "name", "") or "")[:255],
        mime_type=content_type[:100],
        media_type=media_type,
        size_bytes=len(data),
        checksum=checksum,
        bucket_name=settings.MINIO_BUCKET,
        scan_status=scan_status,
    )
    _apply_quota_delta(user, len(data))
    _audit(
        action="MEDIA_UPLOAD_DIRECT", actor=actor, entity_id=media.id,
        new=serialize_media(media), ip=ip,
    )
    return serialize_media(media)


# --- MED-09/10/11 : métadonnées, download, delete ------------------------------


def download_media(*, media: MediaFile, actor, ip) -> str:
    if media.scan_status == MediaFile.ScanStatus.INFECTED:
        raise AuthAPIError(403, "FILE_INFECTED", MSG_INFECTED)
    url = storage.presigned_get_url(media.storage_path)
    MediaAccessLog.objects.create(
        media=media, user=actor, action=MediaAccessLog.Action.DOWNLOAD, ip_address=ip,
    )
    return url


def delete_media(*, media: MediaFile, actor, ip) -> None:
    old = serialize_media(media)
    media_id = media.id
    size = media.size_bytes
    owner = media.owner
    storage.delete_object(media.storage_path)
    media.delete()
    if owner is not None:
        _apply_quota_delta(owner, -size)
    _audit(action="MEDIA_DELETE", actor=actor, entity_id=media_id, old=old, ip=ip)
