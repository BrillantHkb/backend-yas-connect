"""AUTH-R : cache rôle, HasPermission helpers, CRUD rôles / perms / matrice."""

import re
import uuid

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.db.models import Count, Q

from apps.iam.exceptions import AuthAPIError
from apps.iam.models import AuditLog, Permission, Role, RolePermission, User
from apps.iam.services.rbac_catalog import (
    ALL_SYSTEM_CODES,
    CODE_RE,
    ROLE_CODE_RE,
    SELF_PERMISSION_CODES,
    SYSTEM_PERMISSIONS,
)

MSG_FORBIDDEN = "Accès refusé."
MSG_ROLE = "Rôle introuvable."
MSG_PERM = "Permission introuvable."
MSG_USER = "Utilisateur introuvable."
MSG_ROLE_CODE = "Code rôle invalide (SCREAMING_SNAKE, 2–32)."
MSG_PERM_CODE = "Code permission invalide ({module}.{resource}.{action})."
MSG_FIELD = "Champ interdit."
MSG_CODE_IMMUTABLE = "Le code n’est pas modifiable."
MSG_SYSTEM_FROZEN = "Rôle système : level / code gelés."
MSG_ROLE_SYSTEM = "Rôle système : suppression interdite."
MSG_ROLE_IN_USE = "Rôle encore assigné à des utilisateurs."
MSG_ROLE_TAKEN = "Ce code rôle existe déjà."
MSG_PERM_TAKEN = "Ce code permission existe déjà."
MSG_PERM_SYSTEM = "Permission système : suppression interdite."
MSG_PERMS_REQUIRED = "Fournir permission_codes."
MSG_ADMIN_FROZEN = "Les permissions système du rôle ADMIN ne peuvent pas être retirées."
MSG_LAST_ADMIN = "Impossible de rétrograder le dernier administrateur."
MSG_LEVEL = "level doit être un entier entre 0 et 99."

_CODE_RX = re.compile(CODE_RE)
_ROLE_RX = re.compile(ROLE_CODE_RE)


def _cache_key(role_id) -> str:
    return f"rbac:role:{role_id}"


def invalidate_role_cache(role_id) -> None:
    """No-op si Redis / cache down."""
    try:
        cache.delete(_cache_key(role_id))
    except Exception:
        return


def _sql_codes(role_id) -> set[str]:
    return set(
        RolePermission.objects.filter(role_id=role_id).values_list("permission__code", flat=True)
    )


def load_role_perm_codes(role_id) -> set[str]:
    """Cache Redis TTL 60 s ; miss ou cache down → SQL."""
    key = _cache_key(role_id)
    try:
        cached = cache.get(key)
        if cached is not None:
            return set(cached)
    except Exception:
        cached = None
    codes = _sql_codes(role_id)
    try:
        cache.set(key, list(codes), timeout=settings.YAS_RBAC_CACHE_TTL_SECONDS)
    except Exception:
        pass
    return codes


def user_has_permission(user, code: str) -> bool:
    role_id = getattr(user, "role_id", None)
    if role_id is None:
        return False
    return code in load_role_perm_codes(role_id)


def ensure_catalog() -> None:
    """Upsert 58 perms system (idempotent)."""
    if Permission.objects.filter(is_system=True).count() >= 58:
        return
    for row in SYSTEM_PERMISSIONS:
        Permission.objects.get_or_create(
            code=row["code"],
            defaults={
                "name": row["name"],
                "description": row["description"],
                "module": row["module"],
                "resource": row["resource"],
                "action": row["action"],
                "is_system": True,
            },
        )


def _grant_missing(role: Role, codes: frozenset[str]) -> None:
    existing = set(
        RolePermission.objects.filter(role=role).values_list("permission__code", flat=True)
    )
    missing = codes - existing
    if not missing:
        return
    perms = list(Permission.objects.filter(code__in=missing))
    RolePermission.objects.bulk_create(
        [RolePermission(role=role, permission=p) for p in perms]
    )
    invalidate_role_cache(role.id)


def ensure_system_matrix(role: Role | None) -> None:
    """USER/ADMIN sans aucune ligne → lier self / tout. Rôles custom : no-op."""
    if role is None or role.code not in ("USER", "ADMIN"):
        return
    ensure_catalog()
    if RolePermission.objects.filter(role=role).exists():
        return
    wanted = SELF_PERMISSION_CODES if role.code == "USER" else ALL_SYSTEM_CODES
    _grant_missing(role, wanted)


def seed_rbac() -> None:
    """seed_iam : catalogue + USER self + ADMIN tout (ajoute les manquants)."""
    ensure_catalog()
    user_role, _ = Role.objects.get_or_create(
        code="USER",
        defaults={"name": "Utilisateur", "level": 0, "is_system": True},
    )
    admin_role, _ = Role.objects.get_or_create(
        code="ADMIN",
        defaults={"name": "Administrateur", "level": 100, "is_system": True},
    )
    changed = []
    if not user_role.is_system:
        user_role.is_system = True
        changed.append(user_role)
    if not admin_role.is_system:
        admin_role.is_system = True
        changed.append(admin_role)
    if admin_role.level != 100:
        admin_role.level = 100
        changed.append(admin_role)
    for r in changed:
        r.save(update_fields=["is_system", "level", "updated_at"])
    _grant_missing(user_role, SELF_PERMISSION_CODES)
    _grant_missing(admin_role, ALL_SYSTEM_CODES)


def _audit(*, action, actor, entity_id, old=None, new=None, entity_type="roles", ip=None):
    AuditLog.objects.create(
        trace_id=uuid.uuid4(),
        module="IAM",
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        old_values=old,
        new_values=new,
        metadata=None,
        ip_address=ip,
        severity="INFO",
        success=True,
        user=actor,
    )


def _iso(dt):
    return dt.isoformat() if dt else None


def _permission_codes(role: Role) -> list[str]:
    return sorted(
        RolePermission.objects.filter(role=role).values_list("permission__code", flat=True)
    )


def serialize_role(role: Role, *, with_codes: bool) -> dict:
    users_count = User.objects.filter(role=role).count()
    codes = _permission_codes(role)
    data = {
        "id": str(role.id),
        "code": role.code,
        "name": role.name,
        "description": role.description,
        "level": role.level,
        "is_system": role.is_system,
        "users_count": users_count,
        "permissions_count": len(codes),
        "created_at": _iso(role.created_at),
        "updated_at": _iso(role.updated_at),
    }
    if with_codes:
        data["permission_codes"] = codes
    return data


def _parse_limit_offset(request, default=50, maximum=100) -> tuple[int, int]:
    try:
        limit = int(request.query_params.get("limit", default))
    except (TypeError, ValueError) as exc:
        raise AuthAPIError(400, "VALIDATION_ERROR", "Paramètre limit invalide.") from exc
    try:
        offset = int(request.query_params.get("offset", 0))
    except (TypeError, ValueError) as exc:
        raise AuthAPIError(400, "VALIDATION_ERROR", "Paramètre offset invalide.") from exc
    if limit < 1 or limit > maximum:
        raise AuthAPIError(400, "VALIDATION_ERROR", "Paramètre limit invalide.")
    if offset < 0:
        raise AuthAPIError(400, "VALIDATION_ERROR", "Paramètre offset invalide.")
    return limit, offset


def get_role_or_404(role_id) -> Role:
    try:
        return Role.objects.get(pk=role_id)
    except Role.DoesNotExist as exc:
        raise AuthAPIError(404, "ROLE_NOT_FOUND", MSG_ROLE) from exc


def get_permission_or_404(perm_id) -> Permission:
    try:
        return Permission.objects.get(pk=perm_id)
    except Permission.DoesNotExist as exc:
        raise AuthAPIError(404, "PERMISSION_NOT_FOUND", MSG_PERM) from exc


def list_roles(request) -> dict:
    qs = Role.objects.all().annotate(
        users_count=Count("users", distinct=True),
        permissions_count=Count("role_permissions", distinct=True),
    )
    q = (request.query_params.get("q") or "").strip()
    if q:
        qs = qs.filter(Q(code__icontains=q) | Q(name__icontains=q))
    raw_sys = request.query_params.get("is_system")
    if raw_sys is not None and raw_sys != "":
        qs = qs.filter(is_system=str(raw_sys).lower() in ("1", "true", "yes"))
    qs = qs.order_by("-level", "code")
    limit, offset = _parse_limit_offset(request)
    total = qs.count()
    rows = []
    for role in qs[offset : offset + limit]:
        rows.append(
            {
                "id": str(role.id),
                "code": role.code,
                "name": role.name,
                "description": role.description,
                "level": role.level,
                "is_system": role.is_system,
                "users_count": role.users_count,
                "permissions_count": role.permissions_count,
                "created_at": _iso(role.created_at),
                "updated_at": _iso(role.updated_at),
            }
        )
    return {"count": total, "roles": rows}


def _require_name(raw) -> str:
    name = (raw or "").strip()
    if not name or len(name) > 128:
        raise AuthAPIError(400, "VALIDATION_ERROR", "name obligatoire (1–128).")
    return name


def _parse_level(raw, *, default=10) -> int:
    if raw is None:
        return default
    try:
        level = int(raw)
    except (TypeError, ValueError) as exc:
        raise AuthAPIError(400, "VALIDATION_ERROR", MSG_LEVEL) from exc
    if level < 0 or level > 99:
        raise AuthAPIError(400, "VALIDATION_ERROR", MSG_LEVEL)
    return level


def create_role(*, data, actor, ip) -> dict:
    if "is_system" in data:
        raise AuthAPIError(400, "FIELD_FORBIDDEN", MSG_FIELD)
    code = (data.get("code") or "").strip()
    if len(code) < 2 or len(code) > 32 or not _ROLE_RX.fullmatch(code):
        raise AuthAPIError(400, "INVALID_ROLE_CODE", MSG_ROLE_CODE)
    if Role.objects.filter(code=code).exists():
        raise AuthAPIError(409, "ROLE_CODE_TAKEN", MSG_ROLE_TAKEN)
    name = _require_name(data.get("name"))
    description = data.get("description") or ""
    if not isinstance(description, str):
        raise AuthAPIError(400, "VALIDATION_ERROR", "description invalide.")
    level = _parse_level(data.get("level"), default=10)
    role = Role.objects.create(
        code=code,
        name=name,
        description=description,
        level=level,
        is_system=False,
    )
    snap = serialize_role(role, with_codes=True)
    _audit(action="ROLE_CREATE", actor=actor, entity_id=role.id, new=snap, ip=ip)
    return snap


def patch_role(*, role: Role, data, actor, ip) -> dict:
    if "is_system" in data:
        raise AuthAPIError(400, "FIELD_FORBIDDEN", MSG_FIELD)
    if "code" in data:
        raise AuthAPIError(400, "CODE_IMMUTABLE", MSG_CODE_IMMUTABLE)
    keys = [k for k in ("name", "description", "level") if k in data]
    if not keys:
        raise AuthAPIError(400, "VALIDATION_ERROR", "Aucun champ à modifier.")
    if "level" in data and role.is_system:
        raise AuthAPIError(400, "ROLE_SYSTEM_FROZEN", MSG_SYSTEM_FROZEN)
    old = serialize_role(role, with_codes=True)
    if "name" in data:
        role.name = _require_name(data.get("name"))
    if "description" in data:
        description = data.get("description") or ""
        if not isinstance(description, str):
            raise AuthAPIError(400, "VALIDATION_ERROR", "description invalide.")
        role.description = description
    if "level" in data:
        role.level = _parse_level(data.get("level"), default=role.level)
    role.save()
    new = serialize_role(role, with_codes=True)
    _audit(action="ROLE_PATCH", actor=actor, entity_id=role.id, old=old, new=new, ip=ip)
    return new


def delete_role(*, role: Role, actor, ip) -> None:
    if role.is_system:
        raise AuthAPIError(409, "ROLE_SYSTEM", MSG_ROLE_SYSTEM)
    users_count = User.objects.filter(role=role).count()
    if users_count:
        raise AuthAPIError(
            409,
            "ROLE_IN_USE",
            MSG_ROLE_IN_USE,
            extra={"users_count": users_count},
        )
    old = serialize_role(role, with_codes=True)
    role_id = role.id
    _audit(action="ROLE_DELETE", actor=actor, entity_id=role_id, old=old, ip=ip)
    role.delete()
    invalidate_role_cache(role_id)


def serialize_permission(p: Permission) -> dict:
    return {
        "id": str(p.id),
        "code": p.code,
        "name": p.name,
        "description": p.description,
        "module": p.module,
        "resource": p.resource,
        "action": p.action,
        "is_system": p.is_system,
        "created_at": _iso(p.created_at),
        "updated_at": _iso(p.updated_at),
    }


def list_permissions(request) -> dict:
    qs = Permission.objects.all().order_by("code")
    module = (request.query_params.get("module") or "").strip()
    if module:
        qs = qs.filter(module=module)
    limit, offset = _parse_limit_offset(request)
    total = qs.count()
    rows = [serialize_permission(p) for p in qs[offset : offset + limit]]
    return {"count": total, "permissions": rows}


def create_permission(*, data, actor, ip) -> dict:
    if "is_system" in data:
        raise AuthAPIError(400, "FIELD_FORBIDDEN", MSG_FIELD)
    if "code" in data:
        raise AuthAPIError(400, "FIELD_FORBIDDEN", MSG_FIELD)
    module = (data.get("module") or "").strip().lower()
    resource = (data.get("resource") or "").strip().lower()
    action = (data.get("action") or "").strip().lower()
    code = f"{module}.{resource}.{action}"
    if not _CODE_RX.fullmatch(code):
        raise AuthAPIError(400, "INVALID_PERMISSION_CODE", MSG_PERM_CODE)
    if Permission.objects.filter(code=code).exists():
        raise AuthAPIError(409, "PERMISSION_CODE_TAKEN", MSG_PERM_TAKEN)
    name = _require_name(data.get("name"))
    description = data.get("description") or ""
    perm = Permission.objects.create(
        module=module,
        resource=resource,
        action=action,
        code=code,
        name=name,
        description=description,
        is_system=False,
    )
    snap = serialize_permission(perm)
    _audit(
        action="PERMISSION_CREATE",
        actor=actor,
        entity_id=perm.id,
        new=snap,
        entity_type="permissions",
        ip=ip,
    )
    return snap


def delete_permission(*, perm: Permission, actor, ip) -> None:
    if perm.is_system:
        raise AuthAPIError(409, "PERMISSION_SYSTEM", MSG_PERM_SYSTEM)
    role_ids = list(
        RolePermission.objects.filter(permission=perm).values_list("role_id", flat=True)
    )
    old = serialize_permission(perm)
    perm_id = perm.id
    _audit(
        action="PERMISSION_DELETE",
        actor=actor,
        entity_id=perm_id,
        old=old,
        entity_type="permissions",
        ip=ip,
    )
    perm.delete()
    for rid in role_ids:
        invalidate_role_cache(rid)


def _parse_codes(data, *, allow_empty: bool = False) -> list[str]:
    if not isinstance(data, dict) or "permission_codes" not in data:
        raise AuthAPIError(400, "PERMISSIONS_REQUIRED", MSG_PERMS_REQUIRED)
    raw = data.get("permission_codes")
    if not isinstance(raw, list):
        raise AuthAPIError(400, "PERMISSIONS_REQUIRED", MSG_PERMS_REQUIRED)
    if not raw and not allow_empty:
        raise AuthAPIError(400, "PERMISSIONS_REQUIRED", MSG_PERMS_REQUIRED)
    codes = []
    seen = set()
    for item in raw:
        if not isinstance(item, str) or not item.strip():
            raise AuthAPIError(400, "VALIDATION_ERROR", "permission_codes invalide.")
        code = item.strip()
        if code in seen:
            continue
        seen.add(code)
        codes.append(code)
    return codes


def _load_perms_or_404(codes: list[str]) -> list[Permission]:
    perms = list(Permission.objects.filter(code__in=codes))
    found = {p.code for p in perms}
    for code in codes:
        if code not in found:
            raise AuthAPIError(
                404,
                "PERMISSION_NOT_FOUND",
                MSG_PERM,
                extra={"permission": code},
            )
    by_code = {p.code: p for p in perms}
    return [by_code[c] for c in codes]


def _admin_frozen(role: Role, remaining_codes: set[str]) -> None:
    if role.code != "ADMIN":
        return
    system = set(
        Permission.objects.filter(is_system=True).values_list("code", flat=True)
    )
    if not system.issubset(remaining_codes):
        raise AuthAPIError(409, "ADMIN_PERMS_FROZEN", MSG_ADMIN_FROZEN)


@transaction.atomic
def add_role_permissions(*, role: Role, data, actor, ip) -> dict:
    codes = _parse_codes(data)
    perms = _load_perms_or_404(codes)
    existing = set(
        RolePermission.objects.filter(role=role).values_list("permission_id", flat=True)
    )
    added = []
    for perm in perms:
        if perm.id in existing:
            continue
        RolePermission.objects.create(role=role, permission=perm, assigned_by=actor)
        added.append(perm.code)
        existing.add(perm.id)
    invalidate_role_cache(role.id)
    snap = serialize_role(role, with_codes=True)
    _audit(
        action="ROLE_PERM_ADD",
        actor=actor,
        entity_id=role.id,
        new={"added": added, **snap},
        ip=ip,
    )
    return snap


@transaction.atomic
def remove_role_permissions(*, role: Role, data, actor, ip) -> dict:
    codes = _parse_codes(data)
    perms = _load_perms_or_404(codes)
    current = set(_permission_codes(role))
    remaining = current - set(codes)
    _admin_frozen(role, remaining)
    ids = [p.id for p in perms]
    qs = RolePermission.objects.filter(role=role, permission_id__in=ids)
    removed = list(qs.values_list("permission__code", flat=True))
    qs.delete()
    invalidate_role_cache(role.id)
    snap = serialize_role(role, with_codes=True)
    _audit(
        action="ROLE_PERM_REMOVE",
        actor=actor,
        entity_id=role.id,
        old={"removed": removed},
        new=snap,
        ip=ip,
    )
    return snap


@transaction.atomic
def set_role_permissions(*, role: Role, data, actor, ip) -> dict:
    codes = _parse_codes(data, allow_empty=True)
    perms = _load_perms_or_404(codes) if codes else []
    target = set(codes)
    _admin_frozen(role, target)
    old = serialize_role(role, with_codes=True)
    current_ids = set(
        RolePermission.objects.filter(role=role).values_list("permission_id", flat=True)
    )
    target_ids = {p.id for p in perms}
    if target_ids:
        RolePermission.objects.filter(role=role).exclude(permission_id__in=target_ids).delete()
    else:
        RolePermission.objects.filter(role=role).delete()
    for perm in perms:
        if perm.id not in current_ids:
            RolePermission.objects.create(role=role, permission=perm, assigned_by=actor)
    invalidate_role_cache(role.id)
    new = serialize_role(role, with_codes=True)
    _audit(
        action="ROLE_PERMS_SET",
        actor=actor,
        entity_id=role.id,
        old={"permission_codes": old["permission_codes"]},
        new={"permission_codes": new["permission_codes"]},
        ip=ip,
    )
    return new


def assign_user_role(*, user: User, role_code: str, actor, ip) -> dict:
    code = (role_code or "").strip()
    try:
        new_role = Role.objects.get(code=code)
    except Role.DoesNotExist as exc:
        raise AuthAPIError(404, "ROLE_NOT_FOUND", MSG_ROLE) from exc
    old_role = user.role
    if old_role and old_role.code == "ADMIN" and new_role.code != "ADMIN":
        others = User.objects.filter(role__code="ADMIN").exclude(pk=user.pk).exists()
        if not others:
            raise AuthAPIError(409, "LAST_ADMIN", MSG_LAST_ADMIN)
    old = {"role_code": old_role.code if old_role else None}
    user.role = new_role
    user.save(update_fields=["role", "updated_at"])
    new = {"role_code": new_role.code}
    _audit(
        action="USER_ROLE_CHANGE",
        actor=actor,
        entity_id=user.id,
        old=old,
        new=new,
        entity_type="users",
        ip=ip,
    )
    return {"role_code": new_role.code, "role_id": str(new_role.id)}
