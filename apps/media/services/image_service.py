"""MEDIA-B : PATCH image (annotation/flou/dérivé), optimize (stub, MED-19…32)."""

from apps.iam.exceptions import AuthAPIError
from apps.iam.models import User
from apps.media.models import Image, MediaFile
from apps.media.services import storage
from apps.media.services.upload_service import get_own_media_or_404

MSG_NOT_FOUND = "Image introuvable."
MSG_INFECTED = "Fichier rejeté par l'analyse antivirus."


def _get_image_or_404(user: User, pk) -> Image:
    media = get_own_media_or_404(user, pk)
    try:
        return media.image_detail
    except Image.DoesNotExist as exc:
        raise AuthAPIError(404, "NOT_FOUND", MSG_NOT_FOUND) from exc


def serialize_image(image: Image) -> dict:
    return {
        "annotated": image.annotated,
        "blurred": image.blurred,
        "thumbnail_path_url": storage.presigned_get_url(image.thumbnail_path)
        if image.thumbnail_path
        else None,
        "optimized_path_url": storage.presigned_get_url(image.optimized_path)
        if image.optimized_path
        else None,
    }


def update_image(*, user: User, pk, data: dict) -> Image:
    image = _get_image_or_404(user, pk)
    fields = []
    if data.get("derivative_upload_id"):
        derivative = get_own_media_or_404(user, data["derivative_upload_id"])
        if derivative.scan_status == MediaFile.ScanStatus.INFECTED:
            raise AuthAPIError(422, "MEDIA_INFECTED", MSG_INFECTED)
        image.optimized_path = derivative.storage_path
        fields.append("optimized_path")
    if "annotated" in data:
        image.annotated = data["annotated"]
        fields.append("annotated")
    if "blurred" in data:
        image.blurred = data["blurred"]
        fields.append("blurred")
    if fields:
        image.save(update_fields=fields)
    return image


def optimize_image(*, user: User, pk) -> Image:
    image = _get_image_or_404(user, pk)
    if not image.optimized_path:
        image.optimized_path = image.media.storage_path
        image.save(update_fields=["optimized_path"])
    return image
