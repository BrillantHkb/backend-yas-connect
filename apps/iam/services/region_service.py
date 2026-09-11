"""ADMIN-A : CRUD régions. Seed 5 TG déjà dans seed_iam — pas ici."""

import re
import uuid

from apps.iam.exceptions import AuthAPIError
from apps.iam.models import AuditLog, Region, User

MSG_REGION = "Région introuvable."
MSG_CODE = "Code région invalide (SCREAMING_SNAKE, 2–50)."
MSG_NAME = "name obligatoire (1–100)."
MSG_CODE_TAKEN = "Ce code région existe déjà."
MSG_NAME_TAKEN = "Ce libellé région existe déjà."
MSG_CODE_IMMUTABLE = "Le code n’est pas modifiable."
MSG_IN_USE = "Région encore assignée à des utilisateurs."

_CODE_RX = re.compile(r"^[A-Z][A-Z0-9_]*$")


def _iso(dt):
    return dt.isoformat() if dt else None


def _audit(*, action, actor, entity_id, old=None, new=None, metadata=None, ip=None):
    AuditLog.objects.create(
        trace_id=uuid.uuid4(),
        module="IAM",
        action=action,
        entity_type="region",
        entity_id=entity_id,
        old_values=old,
        new_values=new,
        metadata=metadata,
        ip_address=ip,
        severity="INFO",
        success=True,
        user=actor,
    )


def serialize_region(region: Region, *, users_count=None) -> dict:
    data = {
        "id": str(region.id),
        "code": region.code,
        "name": region.name,
        "created_at": _iso(region.created_at),
        "updated_at": _iso(region.updated_at),
    }
    if users_count is not None:
        data["users_count"] = users_count
    return data


def get_region_or_404(region_id) -> Region:
    try:
        return Region.objects.get(pk=region_id)
    except Region.DoesNotExist as exc:
        raise AuthAPIError(404, "NOT_FOUND", MSG_REGION) from exc


def list_regions() -> dict:
    qs = Region.objects.order_by("code")
    rows = [serialize_region(r) for r in qs]
    return {"count": len(rows), "results": rows}


def get_region_detail(region_id) -> dict:
    region = get_region_or_404(region_id)
    return serialize_region(region, users_count=User.objects.filter(region=region).count())


def _require_code(raw) -> str:
    code = (raw or "").strip()
    if len(code) < 2 or len(code) > 50 or not _CODE_RX.fullmatch(code):
        raise AuthAPIError(400, "VALIDATION_ERROR", MSG_CODE)
    return code


def _require_name(raw) -> str:
    name = (raw or "").strip()
    if not name or len(name) > 100:
        raise AuthAPIError(400, "VALIDATION_ERROR", MSG_NAME)
    return name


def create_region(*, data, actor, ip) -> dict:
    code = _require_code(data.get("code"))
    name = _require_name(data.get("name"))
    if Region.objects.filter(code=code).exists():
        raise AuthAPIError(409, "REGION_CODE_TAKEN", MSG_CODE_TAKEN)
    if Region.objects.filter(name=name).exists():
        raise AuthAPIError(409, "REGION_NAME_TAKEN", MSG_NAME_TAKEN)
    region = Region.objects.create(code=code, name=name)
    snap = serialize_region(region)
    _audit(action="REGION_CREATE", actor=actor, entity_id=region.id, new=snap, ip=ip)
    return snap


def patch_region(*, region: Region, data, actor, ip) -> dict:
    if "code" in data:
        raise AuthAPIError(400, "CODE_IMMUTABLE", MSG_CODE_IMMUTABLE)
    if "name" not in data:
        raise AuthAPIError(400, "VALIDATION_ERROR", "Aucun champ à modifier.")
    name = _require_name(data.get("name"))
    if Region.objects.filter(name=name).exclude(pk=region.pk).exists():
        raise AuthAPIError(409, "REGION_NAME_TAKEN", MSG_NAME_TAKEN)
    old = serialize_region(region)
    region.name = name
    region.save(update_fields=["name", "updated_at"])
    new = serialize_region(region)
    _audit(action="REGION_PATCH", actor=actor, entity_id=region.id, old=old, new=new, ip=ip)
    return new


def delete_region(*, region: Region, actor, ip) -> None:
    users_count = User.objects.filter(region=region).count()
    if users_count:
        raise AuthAPIError(
            409,
            "REGION_IN_USE",
            MSG_IN_USE,
            extra={"users_count": users_count},
        )
    old = serialize_region(region)
    region_id = region.id
    region.delete()
    _audit(action="REGION_DELETE", actor=actor, entity_id=region_id, old=old, ip=ip)
