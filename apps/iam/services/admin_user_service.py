"""ADMIN-A : liste filtrée, fiche, create RH, disable/enable, reset MDP, kick."""

import uuid

from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.iam.exceptions import AuthAPIError
from apps.iam.models import AuditLog, Role, User
from apps.iam.services.password_policy import enforce_password_policy
from apps.iam.services.password_service import set_password_with_history
from apps.iam.services.rbac_service import MSG_LAST_ADMIN
from apps.iam.services.register_service import (
    _validate_region_segment,
    suggest_username,
)
from apps.iam.services.security_service import get_user_or_404
from apps.iam.services.session_service import revoke_sessions

MSG_LDAP = "Compte lié à Active Directory."
MSG_SELF = "Action interdite sur votre propre compte."
MSG_PENDING = "Compte encore en attente de validation."
MSG_EMAIL = "Cet e-mail est déjà utilisé."
MSG_MATRICULE = "Ce matricule est déjà utilisé."
MSG_FIELD = "Champ interdit."
MSG_USER = "Utilisateur introuvable."


def _iso(dt):
    return dt.isoformat() if dt else None


def _audit(
    *,
    action: str,
    actor,
    entity_id,
    old=None,
    new=None,
    metadata=None,
    ip=None,
    entity_type="users",
):
    AuditLog.objects.create(
        trace_id=uuid.uuid4(),
        module="IAM",
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        old_values=old,
        new_values=new,
        metadata=metadata,
        ip_address=ip,
        severity="INFO",
        success=True,
        user=actor,
    )


def _parse_bool(raw, name: str):
    if raw is None or raw == "":
        return None
    low = str(raw).lower()
    if low in ("1", "true", "yes"):
        return True
    if low in ("0", "false", "no"):
        return False
    raise AuthAPIError(400, "VALIDATION_ERROR", f"Paramètre {name} invalide.")


def _parse_uuid(raw, name: str):
    if raw is None or raw == "":
        return None
    try:
        return uuid.UUID(str(raw))
    except (TypeError, ValueError) as exc:
        raise AuthAPIError(400, "VALIDATION_ERROR", f"Paramètre {name} invalide.") from exc


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


def _parse_dt(raw, name: str):
    if not raw:
        return None
    dt = parse_datetime(raw)
    if dt is None:
        raise AuthAPIError(400, "VALIDATION_ERROR", f"Paramètre {name} invalide.")
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.utc)
    return dt


def serialize_user_list(u: User) -> dict:
    """Ligne liste : D05 + display_name / matricule / rôle / lock / last_login."""
    role = u.role
    return {
        "id": str(u.id),
        "email": u.email,
        "username": u.username,
        "first_name": u.first_name,
        "last_name": u.last_name,
        "display_name": u.get_full_name(),
        "matricule": u.matricule,
        "role": {"code": role.code, "name": role.name} if role else None,
        "pending_approval": u.pending_approval,
        "is_active": u.is_active,
        "is_locked": u.is_locked,
        "ldap_bound": bool(u.ldap_dn),
        "last_login": _iso(u.last_login),
        "created_at": _iso(u.created_at),
    }


def serialize_user_detail(u: User) -> dict:
    """Fiche admin : liste + coordonnées. Jamais hash / DN / TOTP."""
    data = serialize_user_list(u)
    region = u.region
    data.update(
        {
            "phone": u.phone,
            "job_title": u.job_title,
            "region": (
                {"id": str(region.id), "code": region.code, "name": region.name}
                if region
                else None
            ),
            "segment_id": str(u.segment_id) if u.segment_id else None,
            "first_login": _iso(u.first_login),
            "locked_at": _iso(u.locked_at),
        }
    )
    return data


def _assert_not_self(actor: User, target: User) -> None:
    if actor.pk == target.pk:
        raise AuthAPIError(400, "CANNOT_ACT_ON_SELF", MSG_SELF)


def _assert_not_ldap(user: User) -> None:
    if user.ldap_dn:
        raise AuthAPIError(400, "LDAP_MANAGED", MSG_LDAP)


def _assert_not_last_admin(user: User) -> None:
    role = getattr(user, "role", None)
    if role is None or role.code != "ADMIN":
        return
    others = User.objects.filter(role__code="ADMIN").exclude(pk=user.pk).exists()
    if not others:
        raise AuthAPIError(409, "LAST_ADMIN", MSG_LAST_ADMIN)


def list_users(*, request=None, pending_only: bool = False) -> dict:
    """Filtres ADM-01. pending_only=True = file D05 (si request absent ou pending=true)."""
    qs = User.objects.select_related("role", "region").order_by("created_at")
    if request is None:
        if pending_only:
            qs = qs.filter(pending_approval=True)
        results = [serialize_user_list(u) for u in qs]
        return {"count": len(results), "results": results}

    params = request.query_params
    pending = str(params.get("pending", "")).lower() in ("1", "true", "yes")
    if pending or pending_only:
        qs = qs.filter(pending_approval=True)
    q = (params.get("q") or "").strip()
    if q:
        qs = qs.filter(
            Q(email__icontains=q)
            | Q(username__icontains=q)
            | Q(matricule__icontains=q)
            | Q(first_name__icontains=q)
            | Q(last_name__icontains=q)
        )
    is_active = _parse_bool(params.get("is_active"), "is_active")
    if is_active is not None:
        qs = qs.filter(is_active=is_active)
    is_locked = _parse_bool(params.get("is_locked"), "is_locked")
    if is_locked is not None:
        qs = qs.filter(is_locked=is_locked)
    role_code = (params.get("role_code") or "").strip()
    if role_code:
        qs = qs.filter(role__code=role_code)
    region_id = _parse_uuid(params.get("region_id"), "region_id")
    if region_id is not None:
        qs = qs.filter(region_id=region_id)
    segment_id = _parse_uuid(params.get("segment_id"), "segment_id")
    if segment_id is not None:
        qs = qs.filter(segment_id=segment_id)
    limit, offset = _parse_limit_offset(request)
    total = qs.count()
    rows = [serialize_user_list(u) for u in qs[offset : offset + limit]]
    return {"count": total, "results": rows}


def get_user_detail(user_id) -> dict:
    try:
        user = User.objects.select_related("role", "region").get(pk=user_id)
    except User.DoesNotExist as exc:
        raise AuthAPIError(404, "NOT_FOUND", MSG_USER) from exc
    return serialize_user_detail(user)


def create_local_user(*, data, actor, ip) -> dict:
    """RH hors AD : toujours USER, actif, MFA au 1er login."""
    if "role_code" in data or "role_id" in data:
        raise AuthAPIError(400, "FIELD_FORBIDDEN", MSG_FIELD)
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    first_name = (data.get("first_name") or "").strip()
    last_name = (data.get("last_name") or "").strip()
    phone = data.get("phone")
    job_title = data.get("job_title") or ""
    matricule = data.get("matricule") or None
    if matricule == "":
        matricule = None
    region, segment = _validate_region_segment(
        region_id=data["region_id"],
        segment_id=data["segment_id"],
    )
    if User.objects.filter(email=email).exists():
        raise AuthAPIError(409, "EMAIL_TAKEN", MSG_EMAIL)
    if matricule and User.objects.filter(matricule=matricule).exists():
        raise AuthAPIError(409, "MATRICULE_TAKEN", MSG_MATRICULE)
    username = suggest_username(first_name, last_name)
    enforce_password_policy(password, email=email, username=username)
    role = Role.objects.get(code="USER")
    user = User.objects.create_user(
        email=email,
        password=password,
        username=username,
        role=role,
        first_name=first_name,
        last_name=last_name,
        phone=phone,
        job_title=job_title,
        region=region,
        segment_id=segment.id,
        matricule=matricule,
        ldap_dn=None,
        pending_approval=False,
        is_active=True,
    )
    prefs = user.preferences
    prefs.language = user.language
    prefs.save(update_fields=["language", "last_updated"])
    fiche = serialize_user_detail(user)
    _audit(
        action="USER_CREATE",
        actor=actor,
        entity_id=user.id,
        new={"email": user.email, "username": user.username, "role_code": "USER"},
        ip=ip,
    )
    return fiche


def disable_user(*, user_id, actor, ip, reason="") -> dict:
    user = get_user_or_404(user_id)
    _assert_not_self(actor, user)
    _assert_not_ldap(user)
    _assert_not_last_admin(user)
    old = {"is_active": user.is_active}
    if user.is_active:
        user.is_active = False
        user.save(update_fields=["is_active", "updated_at"])
    revoked = revoke_sessions(user=user, reason="ADMIN")
    metadata = {"revoked": revoked}
    if reason:
        metadata["reason"] = reason
    _audit(
        action="USER_DISABLE",
        actor=actor,
        entity_id=user.id,
        old=old,
        new={"is_active": False},
        metadata=metadata,
        ip=ip,
    )
    user.refresh_from_db()
    return serialize_user_detail(user)


def enable_user(*, user_id, actor, ip, reason="") -> dict:
    user = get_user_or_404(user_id)
    _assert_not_ldap(user)
    if user.pending_approval:
        raise AuthAPIError(400, "STILL_PENDING", MSG_PENDING)
    old = {"is_active": user.is_active}
    if not user.is_active:
        user.is_active = True
        user.save(update_fields=["is_active", "updated_at"])
    metadata = {"reason": reason} if reason else None
    _audit(
        action="USER_ENABLE",
        actor=actor,
        entity_id=user.id,
        old=old,
        new={"is_active": True},
        metadata=metadata,
        ip=ip,
    )
    user.refresh_from_db()
    return serialize_user_detail(user)


def reset_user_password(*, user_id, new_password, actor, ip) -> dict:
    user = get_user_or_404(user_id)
    _assert_not_self(actor, user)
    set_password_with_history(user, new_password)
    revoked = revoke_sessions(user=user, reason="PASSWORD_ADMIN_RESET")
    _audit(
        action="PASSWORD_ADMIN_RESET",
        actor=actor,
        entity_id=user.id,
        metadata={"revoked": revoked},
        ip=ip,
    )
    return {"ok": True}


def revoke_all_sessions(*, user_id, actor, ip) -> dict:
    user = get_user_or_404(user_id)
    _assert_not_self(actor, user)
    revoked = revoke_sessions(user=user, reason="ADMIN")
    _audit(
        action="SESSION_REVOKE_ALL",
        actor=actor,
        entity_id=user.id,
        metadata={"revoked": revoked},
        ip=ip,
    )
    return {"revoked": revoked}


def serialize_audit(row: AuditLog) -> dict:
    return {
        "id": row.id,
        "trace_id": str(row.trace_id),
        "module": row.module,
        "action": row.action,
        "entity_type": row.entity_type,
        "entity_id": str(row.entity_id) if row.entity_id else None,
        "old_values": row.old_values,
        "new_values": row.new_values,
        "metadata": row.metadata,
        "ip_address": row.ip_address,
        "severity": row.severity,
        "success": row.success,
        "created_at": _iso(row.created_at),
        "user_id": str(row.user_id) if row.user_id else None,
        "device_id": str(row.device_id) if row.device_id else None,
    }


def list_audit_logs(*, request) -> dict:
    qs = AuditLog.objects.all().order_by("-created_at")
    params = request.query_params
    user_id = _parse_uuid(params.get("user_id"), "user_id")
    if user_id is not None:
        qs = qs.filter(user_id=user_id)
    entity_type = (params.get("entity_type") or "").strip()
    if entity_type:
        qs = qs.filter(entity_type=entity_type)
    entity_id = _parse_uuid(params.get("entity_id"), "entity_id")
    if entity_id is not None:
        qs = qs.filter(entity_id=entity_id)
    module = (params.get("module") or "").strip()
    if module:
        qs = qs.filter(module=module)
    action = (params.get("action") or "").strip()
    if action:
        qs = qs.filter(action=action)
    success = _parse_bool(params.get("success"), "success")
    if success is not None:
        qs = qs.filter(success=success)
    since = _parse_dt(params.get("from"), "from")
    if since is not None:
        qs = qs.filter(created_at__gte=since)
    until = _parse_dt(params.get("to"), "to")
    if until is not None:
        qs = qs.filter(created_at__lte=until)
    limit, offset = _parse_limit_offset(request)
    total = qs.count()
    rows = [serialize_audit(row) for row in qs[offset : offset + limit]]
    return {"count": total, "results": rows}
