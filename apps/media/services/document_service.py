"""MEDIA-E : GED — créer, lire, modifier, versions, aperçu (MED-55…68)."""

from django.db import transaction

from apps.iam.exceptions import AuthAPIError
from apps.iam.models import User
from apps.media.models import Document, DocumentVersion, MediaFile
from apps.media.services import storage
from apps.media.services.upload_service import get_own_media_or_404

MSG_NOT_FOUND = "Document introuvable."
MSG_USER_NOT_FOUND = "Utilisateur introuvable."
MSG_VALIDATION = "Paramètre invalide."
MSG_ALREADY_DOCUMENT = "Ce fichier est déjà enregistré comme document GED."
MSG_ALREADY_VERSIONED = "Ce fichier est déjà rattaché à une autre version."
MSG_INFECTED = "Fichier rejeté par l'analyse antivirus."
MSG_CONFIDENTIAL = "Document confidentiel."


def _serialize(document: Document) -> dict:
    return {
        "id": str(document.id),
        "title": document.title,
        "category": document.category,
        "confidential": document.confidential,
        "version": document.version,
        "owner_id": str(document.owner_id) if document.owner_id else None,
        "created_at": document.created_at.isoformat(),
    }


def _get_own_document_or_404(user: User, pk) -> Document:
    """Owner-only sur Document.owner (métier GED), distinct de MediaFile.owner (upload)."""
    try:
        document = Document.objects.select_related("media").get(pk=pk)
    except (Document.DoesNotExist, ValueError, TypeError) as exc:
        raise AuthAPIError(404, "NOT_FOUND", MSG_NOT_FOUND) from exc
    if document.owner_id != user.id:
        raise AuthAPIError(404, "NOT_FOUND", MSG_NOT_FOUND)
    return document


def create_document(
    *, user: User, upload_id, title: str, category: str = "", confidential: bool = False
) -> dict:
    media = get_own_media_or_404(user, upload_id)
    if media.scan_status == MediaFile.ScanStatus.INFECTED:
        raise AuthAPIError(422, "MEDIA_INFECTED", MSG_INFECTED)
    if not (title or "").strip():
        raise AuthAPIError(400, "VALIDATION_ERROR", MSG_VALIDATION, extra={"field": "title"})
    if Document.objects.filter(media=media).exists():
        raise AuthAPIError(409, "ALREADY_DOCUMENT", MSG_ALREADY_DOCUMENT)

    with transaction.atomic():
        document = Document.objects.create(
            media=media,
            title=title.strip(),
            category=category or "",
            confidential=bool(confidential),
            version=1,
            owner=user,
        )
        DocumentVersion.objects.create(
            document=document,
            version_number=1,
            media=media,
            changed_by=user,
            comment="Version initiale",
        )
    return _serialize(document)


def get_document(*, user: User, pk) -> dict:
    return _serialize(_get_own_document_or_404(user, pk))


def update_document(*, user: User, pk, data: dict) -> dict:
    document = _get_own_document_or_404(user, pk)
    fields = []
    if "title" in data:
        title = (data["title"] or "").strip()
        if not title:
            raise AuthAPIError(400, "VALIDATION_ERROR", MSG_VALIDATION, extra={"field": "title"})
        document.title = title
        fields.append("title")
    if "category" in data:
        document.category = data["category"] or ""
        fields.append("category")
    if "confidential" in data:
        document.confidential = bool(data["confidential"])
        fields.append("confidential")
    if data.get("owner_id"):
        try:
            new_owner = User.objects.get(pk=data["owner_id"], is_active=True)
        except (User.DoesNotExist, ValueError, TypeError) as exc:
            raise AuthAPIError(404, "NOT_FOUND", MSG_USER_NOT_FOUND) from exc
        document.owner = new_owner
        fields.append("owner")
    if fields:
        document.save(update_fields=fields)
    return _serialize(document)


def add_version(*, user: User, pk, upload_id, comment: str = "") -> dict:
    document = _get_own_document_or_404(user, pk)
    media = get_own_media_or_404(user, upload_id)
    if media.scan_status == MediaFile.ScanStatus.INFECTED:
        raise AuthAPIError(422, "MEDIA_INFECTED", MSG_INFECTED)
    if DocumentVersion.objects.filter(media=media).exists():
        raise AuthAPIError(409, "ALREADY_VERSIONED", MSG_ALREADY_VERSIONED)

    with transaction.atomic():
        next_number = document.version + 1
        version = DocumentVersion.objects.create(
            document=document,
            version_number=next_number,
            media=media,
            changed_by=user,
            comment=comment or "",
        )
        document.version = next_number
        document.save(update_fields=["version"])
    return {
        "version_number": version.version_number,
        "comment": version.comment,
        "created_at": version.created_at.isoformat(),
    }


def list_versions(*, user: User, pk) -> dict:
    document = _get_own_document_or_404(user, pk)
    rows = document.versions.select_related("media", "changed_by").order_by("-version_number")
    return {
        "results": [
            {
                "version_number": v.version_number,
                "media_id": str(v.media_id),
                "comment": v.comment,
                "changed_by": str(v.changed_by_id) if v.changed_by_id else None,
                "created_at": v.created_at.isoformat(),
            }
            for v in rows
        ]
    }


def preview_url(*, user: User, pk) -> str:
    document = _get_own_document_or_404(user, pk)
    # Filet de cohérence contrat : _get_own_document_or_404 est déjà owner-only,
    # donc cette branche n'est jamais atteinte en pratique ce jour (§0 jour 28).
    if document.confidential and document.owner_id != user.id:
        raise AuthAPIError(403, "FORBIDDEN", MSG_CONFIDENTIAL)
    current_version = document.versions.order_by("-version_number").first()
    target_media = current_version.media if current_version else document.media
    return storage.presigned_get_url(target_media.storage_path)
