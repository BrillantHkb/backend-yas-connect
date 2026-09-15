"""ANNUAIRE-B : CRUD admin segment_types / segments, cycle, level, tree. 0 migration."""

import re
import uuid

from django.db.models import Q

from apps.annuaire.models import Segment, SegmentType, UserSegment
from apps.iam.exceptions import AuthAPIError
from apps.iam.models import AuditLog, User

MSG_TYPE_NOT_FOUND = "Type d’unité introuvable."
MSG_SEGMENT_NOT_FOUND = "Segment introuvable."
MSG_CODE = "Code invalide (SCREAMING_SNAKE, 2–64)."
MSG_NAME = "name obligatoire (1–200)."
MSG_LEVEL = "level doit être un entier ≥ 0."
MSG_TYPE_CODE_TAKEN = "Ce code type existe déjà."
MSG_TYPE_NAME_TAKEN = "Ce libellé type existe déjà."
MSG_TYPE_SYSTEM = "Type système (seed) : suppression interdite."
MSG_TYPE_IN_USE = "Type encore utilisé par un segment."
MSG_TYPE_CODE_FROZEN = "Le code n’est pas modifiable."
MSG_SEGMENT_CODE_TAKEN = "Ce code segment existe déjà."
MSG_TYPE_INVALID = "Type d’unité invalide."
MSG_SEGMENT_INVALID = "Segment parent invalide."
MSG_PARENT_SELF = "Un segment ne peut pas être son propre parent."
MSG_CYCLE = "Boucle détectée dans l’arbre."
MSG_LEVEL_INVALID = "Le niveau de l’enfant doit être supérieur à celui du parent."
MSG_RESPONSABLE_INVALID = "Responsable invalide (doit être un utilisateur actif)."
MSG_SEGMENT_IN_USE = "Segment encore utilisé (enfant ou utilisateurs rattachés)."
MSG_VALIDATION = "Paramètre invalide."

SEED_TYPE_CODES = frozenset({"DIRECTION", "DEPARTEMENT", "SERVICE"})
MAX_DEPTH = 16
DEFAULT_LIMIT = 50
MAX_LIMIT = 100

_TYPE_CODE_RX = re.compile(r"^[A-Z][A-Z0-9_]*$")
_SEGMENT_CODE_RX = re.compile(r"^[A-Z][A-Z0-9_-]*$")  # segments : tirets tolérés (ex. NOC-LOME)


def _iso(dt):
    return dt.isoformat() if dt else None


def _audit(*, action, entity_type, actor, entity_id, old=None, new=None, ip=None):
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


def _require_type_code(raw) -> str:
    code = (raw or "").strip()
    if len(code) < 2 or len(code) > 64 or not _TYPE_CODE_RX.fullmatch(code):
        raise AuthAPIError(400, "VALIDATION_ERROR", MSG_CODE)
    return code


def _require_segment_code(raw) -> str:
    code = (raw or "").strip()
    if len(code) < 2 or len(code) > 64 or not _SEGMENT_CODE_RX.fullmatch(code):
        raise AuthAPIError(400, "VALIDATION_ERROR", MSG_CODE)
    return code


def _require_name(raw) -> str:
    name = (raw or "").strip()
    if not name or len(name) > 200:
        raise AuthAPIError(400, "VALIDATION_ERROR", MSG_NAME)
    return name


def _require_level(raw) -> int:
    try:
        level = int(raw)
    except (TypeError, ValueError) as exc:
        raise AuthAPIError(400, "VALIDATION_ERROR", MSG_LEVEL) from exc
    if level < 0:
        raise AuthAPIError(400, "VALIDATION_ERROR", MSG_LEVEL)
    return level


def _parse_uuid(raw, name: str):
    if raw is None or raw == "":
        return None
    try:
        return uuid.UUID(str(raw))
    except (TypeError, ValueError) as exc:
        raise AuthAPIError(
            400, "VALIDATION_ERROR", MSG_VALIDATION, extra={"field": name}
        ) from exc


def _parse_bool(raw, name: str):
    if raw is None or raw == "":
        return None
    low = str(raw).lower()
    if low in ("1", "true", "yes"):
        return True
    if low in ("0", "false", "no"):
        return False
    raise AuthAPIError(400, "VALIDATION_ERROR", MSG_VALIDATION, extra={"field": name})


def _parse_limit_offset(params, *, default=DEFAULT_LIMIT, maximum=MAX_LIMIT) -> tuple[int, int]:
    try:
        limit = int(params.get("limit", default))
    except (TypeError, ValueError) as exc:
        raise AuthAPIError(
            400, "VALIDATION_ERROR", MSG_VALIDATION, extra={"field": "limit"}
        ) from exc
    try:
        offset = int(params.get("offset", 0))
    except (TypeError, ValueError) as exc:
        raise AuthAPIError(
            400, "VALIDATION_ERROR", MSG_VALIDATION, extra={"field": "offset"}
        ) from exc
    if limit < 1 or limit > maximum:
        raise AuthAPIError(400, "VALIDATION_ERROR", MSG_VALIDATION, extra={"field": "limit"})
    if offset < 0:
        raise AuthAPIError(400, "VALIDATION_ERROR", MSG_VALIDATION, extra={"field": "offset"})
    return limit, offset


# --- SegmentType (ANN-06) ----------------------------------------------------


def serialize_segment_type(st: SegmentType) -> dict:
    return {
        "id": str(st.id),
        "code": st.code,
        "name": st.name,
        "level": st.level,
        "description": st.description,
        "is_active": st.is_active,
        "created_at": _iso(st.created_at),
        "updated_at": _iso(st.updated_at),
    }


def get_segment_type_or_404(pk) -> SegmentType:
    try:
        return SegmentType.objects.get(pk=pk)
    except SegmentType.DoesNotExist as exc:
        raise AuthAPIError(404, "NOT_FOUND", MSG_TYPE_NOT_FOUND) from exc


def list_segment_types(request) -> dict:
    params = request.query_params
    qs = SegmentType.objects.order_by("level", "code")
    q = (params.get("q") or "").strip()
    if q:
        qs = qs.filter(Q(code__icontains=q) | Q(name__icontains=q))
    is_active = _parse_bool(params.get("is_active"), "is_active")
    if is_active is not None:
        qs = qs.filter(is_active=is_active)
    limit, offset = _parse_limit_offset(params)
    total = qs.count()
    rows = [serialize_segment_type(t) for t in qs[offset : offset + limit]]
    return {"count": total, "results": rows}


def create_segment_type(*, data, actor, ip) -> dict:
    code = _require_type_code(data.get("code"))
    name = _require_name(data.get("name"))
    level = _require_level(data.get("level", 0))
    description = (data.get("description") or "").strip()
    if SegmentType.objects.filter(code=code).exists():
        raise AuthAPIError(409, "SEGMENT_TYPE_CODE_TAKEN", MSG_TYPE_CODE_TAKEN)
    if SegmentType.objects.filter(name=name).exists():
        raise AuthAPIError(409, "NAME_TAKEN", MSG_TYPE_NAME_TAKEN)
    st = SegmentType.objects.create(code=code, name=name, level=level, description=description)
    snap = serialize_segment_type(st)
    _audit(
        action="SEGMENT_TYPE_CREATE",
        entity_type="segment_types",
        actor=actor,
        entity_id=st.id,
        new=snap,
        ip=ip,
    )
    return snap


def patch_segment_type(*, segment_type: SegmentType, data, actor, ip) -> dict:
    if "code" in data:
        raise AuthAPIError(400, "CODE_IMMUTABLE", MSG_TYPE_CODE_FROZEN)
    allowed = {"name", "level", "description", "is_active"}
    if not (set(data.keys()) & allowed):
        raise AuthAPIError(400, "VALIDATION_ERROR", "Aucun champ à modifier.")
    if set(data.keys()) - allowed:
        raise AuthAPIError(400, "VALIDATION_ERROR", "Champ inconnu.")

    old = serialize_segment_type(segment_type)
    update = []
    if "name" in data:
        name = _require_name(data.get("name"))
        if SegmentType.objects.filter(name=name).exclude(pk=segment_type.pk).exists():
            raise AuthAPIError(409, "NAME_TAKEN", MSG_TYPE_NAME_TAKEN)
        segment_type.name = name
        update.append("name")
    if "level" in data:
        segment_type.level = _require_level(data.get("level"))
        update.append("level")
    if "description" in data:
        segment_type.description = (data.get("description") or "").strip()
        update.append("description")
    if "is_active" in data:
        segment_type.is_active = bool(data.get("is_active"))
        update.append("is_active")

    update.append("updated_at")
    segment_type.save(update_fields=update)
    new = serialize_segment_type(segment_type)
    _audit(
        action="SEGMENT_TYPE_PATCH",
        entity_type="segment_types",
        actor=actor,
        entity_id=segment_type.id,
        old=old,
        new=new,
        ip=ip,
    )
    return new


def delete_segment_type(*, segment_type: SegmentType, actor, ip) -> None:
    if segment_type.code in SEED_TYPE_CODES:
        raise AuthAPIError(409, "TYPE_SYSTEM", MSG_TYPE_SYSTEM)
    if Segment.objects.filter(segment_type=segment_type).exists():
        raise AuthAPIError(409, "TYPE_IN_USE", MSG_TYPE_IN_USE)
    old = serialize_segment_type(segment_type)
    type_id = segment_type.id
    segment_type.delete()
    _audit(
        action="SEGMENT_TYPE_DELETE",
        entity_type="segment_types",
        actor=actor,
        entity_id=type_id,
        old=old,
        ip=ip,
    )


# --- Segment (ANN-07 / 08) ---------------------------------------------------


def _mini_segment(segment: Segment | None) -> dict | None:
    if segment is None:
        return None
    return {"id": str(segment.id), "code": segment.code, "name": segment.name}


def _mini_type(st: SegmentType | None) -> dict | None:
    if st is None:
        return None
    return {"id": str(st.id), "code": st.code, "name": st.name, "level": st.level}


def _mini_user(user: User | None) -> dict | None:
    if user is None:
        return None
    return {"id": str(user.id), "display_name": user.get_full_name(), "username": user.username}


def serialize_segment(segment: Segment, *, children_count=None) -> dict:
    data = {
        "id": str(segment.id),
        "code": segment.code,
        "name": segment.name,
        "description": segment.description,
        "is_active": segment.is_active,
        "type": _mini_type(segment.segment_type),
        "parent": _mini_segment(segment.parent_segment),
        "responsable": _mini_user(segment.responsable),
        "created_at": _iso(segment.created_at),
        "updated_at": _iso(segment.updated_at),
    }
    if children_count is not None:
        data["children_count"] = children_count
    return data


def get_segment_or_404(pk) -> Segment:
    try:
        return Segment.objects.select_related("segment_type", "parent_segment", "responsable").get(
            pk=pk
        )
    except Segment.DoesNotExist as exc:
        raise AuthAPIError(404, "NOT_FOUND", MSG_SEGMENT_NOT_FOUND) from exc


def get_segment_detail(pk) -> dict:
    segment = get_segment_or_404(pk)
    children_count = Segment.objects.filter(parent_segment=segment).count()
    return serialize_segment(segment, children_count=children_count)


def list_segments(request) -> dict:
    params = request.query_params
    qs = Segment.objects.select_related("segment_type", "parent_segment", "responsable")
    q = (params.get("q") or "").strip()
    if q:
        qs = qs.filter(Q(code__icontains=q) | Q(name__icontains=q))
    raw_parent = params.get("parent_id")
    if raw_parent is not None:
        if raw_parent == "null":
            qs = qs.filter(parent_segment_id__isnull=True)
        else:
            parent_id = _parse_uuid(raw_parent, "parent_id")
            qs = qs.filter(parent_segment_id=parent_id)
    type_id = _parse_uuid(params.get("type_id"), "type_id")
    if type_id is not None:
        qs = qs.filter(segment_type_id=type_id)
    is_active = _parse_bool(params.get("is_active"), "is_active")
    if is_active is not None:
        qs = qs.filter(is_active=is_active)
    limit, offset = _parse_limit_offset(params)
    qs = qs.order_by("code")
    total = qs.count()
    rows = [serialize_segment(s) for s in qs[offset : offset + limit]]
    return {"count": total, "results": rows}


def _resolve_type(raw_type_id) -> SegmentType | None:
    if raw_type_id is None:
        return None
    try:
        return SegmentType.objects.get(pk=raw_type_id)
    except SegmentType.DoesNotExist as exc:
        raise AuthAPIError(400, "TYPE_INVALID", MSG_TYPE_INVALID) from exc


def _resolve_responsable(raw_user_id) -> User | None:
    if raw_user_id is None:
        return None
    user = User.objects.filter(pk=raw_user_id).first()
    if user is None or not user.is_active:
        raise AuthAPIError(400, "RESPONSABLE_INVALID", MSG_RESPONSABLE_INVALID)
    return user


def _resolve_parent(*, segment_id, raw_parent_id) -> Segment | None:
    """None = racine. Sinon existe, pas soi, pas de cycle (max 16 sauts)."""
    if raw_parent_id is None:
        return None
    if segment_id is not None and str(raw_parent_id) == str(segment_id):
        raise AuthAPIError(400, "SEGMENT_PARENT_SELF", MSG_PARENT_SELF)
    try:
        parent = Segment.objects.select_related("segment_type").get(pk=raw_parent_id)
    except Segment.DoesNotExist as exc:
        raise AuthAPIError(400, "SEGMENT_INVALID", MSG_SEGMENT_INVALID) from exc
    if segment_id is not None:
        seen = {str(segment_id)}
        cur = parent
        hops = 0
        while cur is not None:
            if str(cur.id) in seen:
                raise AuthAPIError(400, "SEGMENT_CYCLE", MSG_CYCLE)
            seen.add(str(cur.id))
            hops += 1
            if hops > MAX_DEPTH:
                raise AuthAPIError(400, "SEGMENT_CYCLE", MSG_CYCLE)
            cur = cur.parent_segment
    return parent


def _check_level(*, parent: Segment | None, segment_type: SegmentType | None) -> None:
    if parent is None or parent.segment_type is None or segment_type is None:
        return
    if segment_type.level <= parent.segment_type.level:
        raise AuthAPIError(400, "SEGMENT_LEVEL_INVALID", MSG_LEVEL_INVALID)


def create_segment(*, data, actor, ip) -> dict:
    code = _require_segment_code(data.get("code"))
    name = _require_name(data.get("name"))
    description = (data.get("description") or "").strip()
    if Segment.objects.filter(code=code).exists():
        raise AuthAPIError(409, "SEGMENT_CODE_TAKEN", MSG_SEGMENT_CODE_TAKEN)
    segment_type = _resolve_type(data.get("segment_type_id"))
    parent = _resolve_parent(segment_id=None, raw_parent_id=data.get("parent_segment_id"))
    _check_level(parent=parent, segment_type=segment_type)
    responsable = _resolve_responsable(data.get("responsable_id"))
    is_active = data.get("is_active", True)

    segment = Segment.objects.create(
        code=code,
        name=name,
        description=description,
        segment_type=segment_type,
        parent_segment=parent,
        responsable=responsable,
        is_active=bool(is_active),
    )
    snap = serialize_segment(segment, children_count=0)
    _audit(
        action="SEGMENT_CREATE",
        entity_type="segments",
        actor=actor,
        entity_id=segment.id,
        new=snap,
        ip=ip,
    )
    return snap


def patch_segment(*, segment: Segment, data, actor, ip) -> dict:
    allowed = {
        "code",
        "name",
        "description",
        "segment_type_id",
        "parent_segment_id",
        "responsable_id",
        "is_active",
    }
    if not data:
        raise AuthAPIError(400, "VALIDATION_ERROR", "Aucun champ à modifier.")
    if set(data.keys()) - allowed:
        raise AuthAPIError(400, "VALIDATION_ERROR", "Champ inconnu.")

    old = serialize_segment(segment)
    update = []

    if "code" in data:
        code = _require_segment_code(data.get("code"))
        if Segment.objects.filter(code=code).exclude(pk=segment.pk).exists():
            raise AuthAPIError(409, "SEGMENT_CODE_TAKEN", MSG_SEGMENT_CODE_TAKEN)
        segment.code = code
        update.append("code")

    if "name" in data:
        segment.name = _require_name(data.get("name"))
        update.append("name")

    if "description" in data:
        segment.description = (data.get("description") or "").strip()
        update.append("description")

    new_type = segment.segment_type
    if "segment_type_id" in data:
        new_type = _resolve_type(data.get("segment_type_id"))
        segment.segment_type = new_type
        update.append("segment_type")

    new_parent = segment.parent_segment
    if "parent_segment_id" in data:
        new_parent = _resolve_parent(
            segment_id=segment.id, raw_parent_id=data.get("parent_segment_id")
        )
        segment.parent_segment = new_parent
        update.append("parent_segment")

    if "segment_type_id" in data or "parent_segment_id" in data:
        _check_level(parent=new_parent, segment_type=new_type)

    if "responsable_id" in data:
        segment.responsable = _resolve_responsable(data.get("responsable_id"))
        update.append("responsable")

    if "is_active" in data:
        segment.is_active = bool(data.get("is_active"))
        update.append("is_active")

    if not update:
        raise AuthAPIError(400, "VALIDATION_ERROR", "Aucun champ à modifier.")

    update.append("updated_at")
    segment.save(update_fields=update)
    new = serialize_segment(segment)
    _audit(
        action="SEGMENT_PATCH",
        entity_type="segments",
        actor=actor,
        entity_id=segment.id,
        old=old,
        new=new,
        ip=ip,
    )
    return new


def delete_segment(*, segment: Segment, actor, ip) -> None:
    if Segment.objects.filter(parent_segment=segment).exists():
        raise AuthAPIError(409, "SEGMENT_IN_USE", MSG_SEGMENT_IN_USE)
    if User.objects.filter(segment_id=segment.id).exists():
        raise AuthAPIError(409, "SEGMENT_IN_USE", MSG_SEGMENT_IN_USE)
    if UserSegment.objects.filter(segment=segment).exists():
        raise AuthAPIError(409, "SEGMENT_IN_USE", MSG_SEGMENT_IN_USE)
    old = serialize_segment(segment)
    segment_id = segment.id
    segment.delete()
    _audit(
        action="SEGMENT_DELETE",
        entity_type="segments",
        actor=actor,
        entity_id=segment_id,
        old=old,
        ip=ip,
    )


# --- Arbre (ANN-08) ----------------------------------------------------------


def _serialize_tree_node(segment: Segment, *, include_inactive: bool) -> dict:
    data = {
        "id": str(segment.id),
        "code": segment.code,
        "name": segment.name,
        "description": segment.description,
        "is_active": segment.is_active,
        "type": _mini_type(segment.segment_type),
        "parent": _mini_segment(segment.parent_segment),
        "responsable": _mini_user(segment.responsable),
    }
    children_qs = segment.children.select_related("segment_type", "parent_segment", "responsable")
    if not include_inactive:
        children_qs = children_qs.filter(is_active=True)
    data["children"] = [
        _serialize_tree_node(child, include_inactive=include_inactive)
        for child in children_qs.order_by("code")
    ]
    return data


def get_tree(request) -> list:
    params = request.query_params
    include_inactive = _parse_bool(params.get("include_inactive"), "include_inactive") or False
    root_id = _parse_uuid(params.get("root_id"), "root_id")

    qs = Segment.objects.select_related("segment_type", "parent_segment", "responsable")
    if root_id is not None:
        roots = list(qs.filter(pk=root_id))
    else:
        roots = list(qs.filter(parent_segment_id__isnull=True))
        if not include_inactive:
            roots = [r for r in roots if r.is_active]
    roots.sort(key=lambda s: s.code)
    return [_serialize_tree_node(r, include_inactive=include_inactive) for r in roots]
