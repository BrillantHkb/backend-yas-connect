"""ANNUAIRE-D : CRUD skills + certifications, self et admin (ANN-14, 15, 17, 18)."""

import uuid

from django.utils import timezone

from apps.annuaire.models import UserCertification, UserSkill
from apps.iam.exceptions import AuthAPIError
from apps.iam.models import AuditLog, User
from apps.media.models import MediaFile

MSG_VALIDATION = "Paramètre invalide."
MSG_SKILL_TAKEN = "Compétence déjà déclarée."
MSG_SKILL_LEVEL_INVALID = "level doit être un entier entre 1 et 5."
MSG_SKILL_LIMIT = "Nombre maximum de compétences atteint (50)."
MSG_SKILL_NOT_FOUND = "Compétence introuvable."
MSG_CERT_DATE_INVALID = "issued_at ne peut pas être dans le futur."
MSG_CERT_LIMIT = "Nombre maximum de certifications atteint (30)."
MSG_CERT_DOCUMENT_INVALID = "document_id invalide."
MSG_CERT_NOT_FOUND = "Certification introuvable."

_SKILL_LIMIT = 50
_CERT_LIMIT = 30
_VISIBLE_SCAN = frozenset({MediaFile.ScanStatus.CLEAN, MediaFile.ScanStatus.SKIPPED})


def _audit(*, action, actor, entity_type, entity_id, old=None, new=None, ip=None):
    AuditLog.objects.create(
        trace_id=uuid.uuid4(),
        module="ANNUAIRE",
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        old_values=old,
        new_values=new,
        ip_address=ip,
        severity="INFO",
        success=True,
        user=actor,
    )


# --- Skills (ANN-14, 17) -----------------------------------------------------


def serialize_skill(row: UserSkill) -> dict:
    return {"id": str(row.id), "skill_name": row.skill_name, "level": row.level}


def list_skills(user: User) -> dict:
    rows = UserSkill.objects.filter(user=user).order_by("skill_name")
    return {"count": rows.count(), "results": [serialize_skill(r) for r in rows]}


def get_own_skill_or_404(user: User, pk) -> UserSkill:
    try:
        return UserSkill.objects.get(pk=pk, user=user)
    except UserSkill.DoesNotExist as exc:
        raise AuthAPIError(404, "NOT_FOUND", MSG_SKILL_NOT_FOUND) from exc


def get_skill_or_404(pk) -> UserSkill:
    try:
        return UserSkill.objects.get(pk=pk)
    except UserSkill.DoesNotExist as exc:
        raise AuthAPIError(404, "NOT_FOUND", MSG_SKILL_NOT_FOUND) from exc


def _check_level(level) -> int:
    if isinstance(level, bool) or not isinstance(level, int) or level < 1 or level > 5:
        raise AuthAPIError(400, "SKILL_LEVEL_INVALID", MSG_SKILL_LEVEL_INVALID)
    return level


def create_skill(*, user: User, data, actor, ip) -> dict:
    skill_name = (data.get("skill_name") or "").strip()
    if not skill_name:
        raise AuthAPIError(400, "VALIDATION_ERROR", MSG_VALIDATION, extra={"field": "skill_name"})
    level = _check_level(data.get("level", 1) if data.get("level") is not None else 1)
    if UserSkill.objects.filter(user=user, skill_name__iexact=skill_name).exists():
        raise AuthAPIError(409, "SKILL_TAKEN", MSG_SKILL_TAKEN)
    if UserSkill.objects.filter(user=user).count() >= _SKILL_LIMIT:
        raise AuthAPIError(400, "SKILL_LIMIT", MSG_SKILL_LIMIT)
    row = UserSkill.objects.create(user=user, skill_name=skill_name, level=level)
    _audit(
        action="USER_SKILL_CREATE", actor=actor, entity_type="user_skills",
        entity_id=row.id, new=serialize_skill(row), ip=ip,
    )
    return serialize_skill(row)


def patch_skill(*, row: UserSkill, data, actor, ip) -> dict:
    allowed = {"skill_name", "level"}
    if not data:
        raise AuthAPIError(400, "VALIDATION_ERROR", "Aucun champ à modifier.")
    if set(data.keys()) - allowed:
        raise AuthAPIError(400, "VALIDATION_ERROR", "Champ inconnu.")

    old = serialize_skill(row)
    update = []

    if "skill_name" in data:
        name = (data.get("skill_name") or "").strip()
        if not name:
            raise AuthAPIError(
                400, "VALIDATION_ERROR", MSG_VALIDATION, extra={"field": "skill_name"}
            )
        dupe = UserSkill.objects.filter(user=row.user, skill_name__iexact=name)
        if dupe.exclude(pk=row.pk).exists():
            raise AuthAPIError(409, "SKILL_TAKEN", MSG_SKILL_TAKEN)
        row.skill_name = name
        update.append("skill_name")

    if "level" in data:
        row.level = _check_level(data.get("level"))
        update.append("level")

    if not update:
        raise AuthAPIError(400, "VALIDATION_ERROR", "Aucun champ à modifier.")

    update.append("updated_at")
    row.save(update_fields=update)
    _audit(
        action="USER_SKILL_UPDATE", actor=actor, entity_type="user_skills",
        entity_id=row.id, old=old, new=serialize_skill(row), ip=ip,
    )
    return serialize_skill(row)


def delete_skill(*, row: UserSkill, actor, ip) -> None:
    old = serialize_skill(row)
    row_id = row.id
    row.delete()
    _audit(
        action="USER_SKILL_DELETE", actor=actor, entity_type="user_skills",
        entity_id=row_id, old=old, ip=ip,
    )


# --- Certifications (ANN-15, 18) ---------------------------------------------


def _document_card(media_id) -> dict | None:
    if not media_id:
        return None
    media = MediaFile.objects.filter(pk=media_id).first()
    if media is None or media.scan_status not in _VISIBLE_SCAN:
        return None
    return {"id": str(media.id), "url": f"/api/v1/media/files/{media.id}"}


def serialize_certification(row: UserCertification) -> dict:
    data = {
        "id": str(row.id),
        "certification_name": row.certification_name,
        "issued_at": row.issued_at.isoformat() if row.issued_at else None,
        "document_id": str(row.document_id) if row.document_id else None,
    }
    document = _document_card(row.document_id)
    if document is not None:
        data["document"] = document
    return data


def list_certifications(user: User) -> dict:
    rows = UserCertification.objects.filter(user=user).order_by("certification_name")
    return {"count": rows.count(), "results": [serialize_certification(r) for r in rows]}


def get_own_certification_or_404(user: User, pk) -> UserCertification:
    try:
        return UserCertification.objects.get(pk=pk, user=user)
    except UserCertification.DoesNotExist as exc:
        raise AuthAPIError(404, "NOT_FOUND", MSG_CERT_NOT_FOUND) from exc


def get_certification_or_404(pk) -> UserCertification:
    try:
        return UserCertification.objects.get(pk=pk)
    except UserCertification.DoesNotExist as exc:
        raise AuthAPIError(404, "NOT_FOUND", MSG_CERT_NOT_FOUND) from exc


def _check_issued_at(issued_at):
    if issued_at is None:
        return None
    if issued_at > timezone.localdate():
        raise AuthAPIError(400, "CERT_DATE_INVALID", MSG_CERT_DATE_INVALID)
    return issued_at


def _check_document(document_id, target_user: User) -> MediaFile | None:
    if not document_id:
        return None
    try:
        media = MediaFile.objects.get(pk=document_id)
    except MediaFile.DoesNotExist as exc:
        raise AuthAPIError(400, "CERT_DOCUMENT_INVALID", MSG_CERT_DOCUMENT_INVALID) from exc
    if (
        media.owner_id != target_user.id
        or media.scan_status not in _VISIBLE_SCAN
        or media.media_type != MediaFile.MediaType.DOCUMENT
    ):
        raise AuthAPIError(400, "CERT_DOCUMENT_INVALID", MSG_CERT_DOCUMENT_INVALID)
    return media


def create_certification(*, user: User, data, actor, ip) -> dict:
    name = (data.get("certification_name") or "").strip()
    if not name:
        raise AuthAPIError(
            400, "VALIDATION_ERROR", MSG_VALIDATION, extra={"field": "certification_name"}
        )
    issued_at = _check_issued_at(data.get("issued_at"))
    document = _check_document(data.get("document_id"), user)
    if UserCertification.objects.filter(user=user).count() >= _CERT_LIMIT:
        raise AuthAPIError(400, "CERT_LIMIT", MSG_CERT_LIMIT)
    row = UserCertification.objects.create(
        user=user, certification_name=name, issued_at=issued_at, document=document,
    )
    _audit(
        action="USER_CERTIFICATION_CREATE", actor=actor, entity_type="user_certifications",
        entity_id=row.id, new=serialize_certification(row), ip=ip,
    )
    return serialize_certification(row)


def patch_certification(*, row: UserCertification, data, actor, ip) -> dict:
    allowed = {"certification_name", "issued_at", "document_id"}
    if not data:
        raise AuthAPIError(400, "VALIDATION_ERROR", "Aucun champ à modifier.")
    if set(data.keys()) - allowed:
        raise AuthAPIError(400, "VALIDATION_ERROR", "Champ inconnu.")

    old = serialize_certification(row)
    update = []

    if "certification_name" in data:
        name = (data.get("certification_name") or "").strip()
        if not name:
            raise AuthAPIError(
                400, "VALIDATION_ERROR", MSG_VALIDATION, extra={"field": "certification_name"}
            )
        row.certification_name = name
        update.append("certification_name")

    if "issued_at" in data:
        row.issued_at = _check_issued_at(data.get("issued_at"))
        update.append("issued_at")

    if "document_id" in data:
        row.document = _check_document(data.get("document_id"), row.user)
        update.append("document")

    if not update:
        raise AuthAPIError(400, "VALIDATION_ERROR", "Aucun champ à modifier.")

    row.save(update_fields=update)
    _audit(
        action="USER_CERTIFICATION_UPDATE", actor=actor, entity_type="user_certifications",
        entity_id=row.id, old=old, new=serialize_certification(row), ip=ip,
    )
    return serialize_certification(row)


def delete_certification(*, row: UserCertification, actor, ip) -> None:
    old = serialize_certification(row)
    row_id = row.id
    row.delete()
    _audit(
        action="USER_CERTIFICATION_DELETE", actor=actor, entity_type="user_certifications",
        entity_id=row_id, old=old, ip=ip,
    )
