"""MEDIA-C : transcodage (stub synchrone), stream, miniature (MED-33…42)."""

from apps.iam.exceptions import AuthAPIError
from apps.iam.models import User
from apps.media.models import Video
from apps.media.services import storage
from apps.media.services.upload_service import get_own_media_or_404

MSG_NOT_FOUND = "Vidéo introuvable."
MSG_NOT_READY = "Vidéo pas encore transcodée."


def _get_video_or_404(user: User, pk) -> Video:
    media = get_own_media_or_404(user, pk)
    try:
        return media.video_detail
    except Video.DoesNotExist as exc:
        raise AuthAPIError(404, "NOT_FOUND", MSG_NOT_FOUND) from exc


def transcode(*, user: User, pk) -> Video:
    """Stub synchrone : PENDING→PROCESSING→READY dans la même requête (§0 jour 28)."""
    video = _get_video_or_404(user, pk)
    video.transcoding_status = Video.TranscodingStatus.PROCESSING
    video.save(update_fields=["transcoding_status"])

    video.transcoding_status = Video.TranscodingStatus.READY
    video.streaming_ready = True
    if not video.thumbnail_path:
        video.thumbnail_path = video.media.storage_path
    video.save(update_fields=["transcoding_status", "streaming_ready", "thumbnail_path"])
    return video


def stream_url(*, user: User, pk) -> str:
    video = _get_video_or_404(user, pk)
    if video.transcoding_status != Video.TranscodingStatus.READY:
        raise AuthAPIError(409, "VIDEO_NOT_READY", MSG_NOT_READY)
    return storage.presigned_get_url(video.media.storage_path)


def thumbnail_url(*, user: User, pk) -> str:
    video = _get_video_or_404(user, pk)
    if not video.thumbnail_path:
        raise AuthAPIError(404, "NOT_FOUND", MSG_NOT_FOUND)
    return storage.presigned_get_url(video.thumbnail_path)
