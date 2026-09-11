"""PROF-A : upload / clear avatar. Scan SKIPPED lab. Fichier conservé au DELETE."""

import uuid
from pathlib import Path

from django.conf import settings

from apps.iam.exceptions import AuthAPIError
from apps.iam.models import AuditLog, User
from apps.media.models import MediaFile

MSG_INVALID = "Fichier image invalide."
MSG_TOO_LARGE = "Image trop volumineuse."
MSG_INFECTED = "Fichier rejeté par l’analyse antivirus."
MSG_NOT_FOUND = "Fichier introuvable."

_ALLOWED = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}
_VISIBLE = frozenset(
    {MediaFile.ScanStatus.CLEAN, MediaFile.ScanStatus.SKIPPED}
)


def avatar_url(user: User) -> str | None:
    if not user.avatar_id:
        return None
    media = MediaFile.objects.filter(pk=user.avatar_id).first()
    if media is None or media.scan_status not in _VISIBLE:
        return None
    return f"/api/v1/media/files/{media.id}"


def get_visible_media(media_id) -> MediaFile:
    try:
        media = MediaFile.objects.get(pk=media_id)
    except MediaFile.DoesNotExist as exc:
        raise AuthAPIError(404, "NOT_FOUND", MSG_NOT_FOUND) from exc
    if media.scan_status not in _VISIBLE:
        raise AuthAPIError(404, "NOT_FOUND", MSG_NOT_FOUND)
    path = Path(settings.MEDIA_ROOT) / media.storage_path
    if not path.is_file():
        raise AuthAPIError(404, "NOT_FOUND", MSG_NOT_FOUND)
    return media


def media_abs_path(media: MediaFile) -> Path:
    return Path(settings.MEDIA_ROOT) / media.storage_path


def upload_avatar(*, user: User, uploaded, actor, ip) -> dict:
    content_type = (getattr(uploaded, "content_type", None) or "").split(";")[0].strip().lower()
    if content_type not in _ALLOWED:
        raise AuthAPIError(400, "INVALID_MEDIA", MSG_INVALID)
    size = int(getattr(uploaded, "size", 0) or 0)
    max_bytes = settings.YAS_AVATAR_MAX_BYTES
    if size > max_bytes:
        raise AuthAPIError(400, "AVATAR_TOO_LARGE", MSG_TOO_LARGE)
    data = uploaded.read()
    if len(data) > max_bytes:
        raise AuthAPIError(400, "AVATAR_TOO_LARGE", MSG_TOO_LARGE)
    if settings.YAS_MEDIA_AVATAR_SCAN_SKIP:
        scan = MediaFile.ScanStatus.SKIPPED
        virus_scanned = False
    else:
        scan = MediaFile.ScanStatus.PENDING
        virus_scanned = False
    if scan == MediaFile.ScanStatus.INFECTED:
        raise AuthAPIError(400, "MEDIA_INFECTED", MSG_INFECTED)

    media_id = uuid.uuid4()
    ext = _ALLOWED[content_type]
    rel = Path("avatars") / str(user.id) / f"{media_id}{ext}"
    dest = Path(settings.MEDIA_ROOT) / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)

    media = MediaFile.objects.create(
        id=media_id,
        owner=user,
        storage_path=rel.as_posix(),
        original_name=(getattr(uploaded, "name", "") or "")[:255],
        mime_type=content_type,
        media_type=MediaFile.MediaType.IMAGE,
        size_bytes=len(data),
        scan_status=scan,
        virus_scanned=virus_scanned,
    )
    if media.scan_status in _VISIBLE:
        user.avatar_id = media.id
        user.save(update_fields=["avatar_id", "updated_at"])
    AuditLog.objects.create(
        trace_id=media.id,
        module="IAM",
        action="AVATAR_SET",
        entity_type="users",
        entity_id=user.id,
        new_values={"avatar_id": str(media.id)},
        ip_address=ip,
        severity="INFO",
        success=True,
        user=actor,
    )
    return {"avatar_id": str(media.id), "avatar_url": avatar_url(user)}


def clear_avatar(*, user: User, actor, ip) -> None:
    old = str(user.avatar_id) if user.avatar_id else None
    user.avatar_id = None
    user.save(update_fields=["avatar_id", "updated_at"])
    AuditLog.objects.create(
        trace_id=user.id,
        module="IAM",
        action="AVATAR_CLEAR",
        entity_type="users",
        entity_id=user.id,
        old_values={"avatar_id": old},
        ip_address=ip,
        severity="INFO",
        success=True,
        user=actor,
    )
