"""ANNUAIRE-C : open_assignment, sync_users_segment_id, validate_org_fk (ANN-09…13, 16)."""

import uuid

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.annuaire.models import Segment, UserSegment
from apps.iam.exceptions import AuthAPIError
from apps.iam.models import AuditLog, Region, User

MSG_REGION_INVALID = "Région invalide."
MSG_SEGMENT_INVALID = "Segment invalide."
MSG_NOT_FOUND = "Affectation introuvable."
MSG_USER_NOT_FOUND = "Utilisateur introuvable."
MSG_DATE_INVALID = "start_date doit être antérieure ou égale à end_date."
MSG_VALIDATION = "Paramètre invalide."
MSG_USER_ID_FROZEN = "user_id n’est pas modifiable."


def _iso(dt):
    return dt.isoformat() if dt else None


def _audit(*, action, actor, entity_id, old=None, new=None, ip=None):
    AuditLog.objects.create(
        trace_id=uuid.uuid4(),
        module="ANNUAIRE",
        action=action,
        entity_type="user_segments",
        entity_id=entity_id,
        old_values=old,
        new_values=new,
        ip_address=ip,
        severity="INFO",
        success=True,
        user=actor,
    )


def _mini_user(user: User | None) -> dict | None:
    if user is None:
        return None
    return {"id": str(user.id), "display_name": user.get_full_name(), "username": user.username}


def serialize_assignment(row: UserSegment) -> dict:
    return {
        "id": str(row.id),
        "segment": {"id": str(row.segment_id), "code": row.segment.code, "name": row.segment.name},
        "start_date": _iso(row.start_date),
        "end_date": _iso(row.end_date),
        "is_active": row.is_active,
        "position": row.position,
        "position_description": row.position_description,
        "assigned_by": _mini_user(row.assigned_by),
    }


def _parse_dt(raw):
    if raw is None or raw == "":
        return None
    if not isinstance(raw, str):
        dt = raw
    else:
        dt = parse_datetime(raw)
        if dt is None:
            raise AuthAPIError(400, "VALIDATION_ERROR", MSG_VALIDATION, extra={"field": "date"})
    return dt if timezone.is_aware(dt) else timezone.make_aware(dt)


def _parse_bool(raw, name):
    if raw is None or raw == "":
        return None
    low = str(raw).lower()
    if low in ("1", "true", "yes"):
        return True
    if low in ("0", "false", "no"):
        return False
    raise AuthAPIError(400, "VALIDATION_ERROR", MSG_VALIDATION, extra={"field": name})


# --- ANN-16 : FK org partagée -----------------------------------------------


def validate_org_fk(*, region_id, segment_id) -> tuple[Region, Segment]:
    """Obligatoires D02/D03/ADM-02. 400 métier (pas 404) pour ne pas leak l’existence."""
    try:
        region = Region.objects.get(pk=region_id)
    except Region.DoesNotExist as exc:
        raise AuthAPIError(400, "REGION_INVALID", MSG_REGION_INVALID) from exc
    try:
        segment = Segment.objects.get(pk=segment_id, is_active=True)
    except Segment.DoesNotExist as exc:
        raise AuthAPIError(400, "SEGMENT_INVALID", MSG_SEGMENT_INVALID) from exc
    return region, segment


# --- ANN-13 : sync -----------------------------------------------------------


def sync_users_segment_id(user: User) -> None:
    row = (
        UserSegment.objects.filter(user=user, is_active=True, end_date__isnull=True)
        .order_by("-start_date")
        .first()
    )
    user.segment_id = row.segment_id if row else None
    user.save(update_fields=["segment_id", "updated_at"])


def open_assignment(
    user: User,
    segment: Segment,
    *,
    assigned_by: User | None = None,
    start_date=None,
    position: str = "",
    position_description: str = "",
) -> UserSegment:
    """Clôture l’ouverte existante (si présente) → INSERT → sync (même transaction)."""
    start_date = start_date or timezone.now()
    previous = UserSegment.objects.filter(
        user=user, is_active=True, end_date__isnull=True
    ).first()
    if previous is not None:
        old = serialize_assignment(previous)
        previous.end_date = start_date
        previous.is_active = False
        previous.save(update_fields=["end_date", "is_active", "updated_at"])
        _audit(
            action="USER_SEGMENT_CLOSE",
            actor=assigned_by,
            entity_id=previous.id,
            old=old,
            new=serialize_assignment(previous),
        )
    row = UserSegment.objects.create(
        user=user,
        segment=segment,
        assigned_by=assigned_by,
        start_date=start_date,
        position=position or "",
        position_description=position_description or "",
        is_active=True,
    )
    sync_users_segment_id(user)
    _audit(
        action="USER_SEGMENT_CREATE",
        actor=assigned_by,
        entity_id=row.id,
        new=serialize_assignment(row),
    )
    return row


# --- ANN-09…12 : CRUD historique --------------------------------------------


def get_target_user_or_404(user_id) -> User:
    try:
        return User.objects.get(pk=user_id)
    except User.DoesNotExist as exc:
        raise AuthAPIError(404, "NOT_FOUND", MSG_USER_NOT_FOUND) from exc


def get_user_segment_or_404(pk) -> UserSegment:
    try:
        return UserSegment.objects.select_related("user", "segment", "assigned_by").get(pk=pk)
    except UserSegment.DoesNotExist as exc:
        raise AuthAPIError(404, "NOT_FOUND", MSG_NOT_FOUND) from exc


def list_assignments(user: User, request) -> dict:
    params = request.query_params
    include_closed = _parse_bool(params.get("include_closed"), "include_closed")
    qs = UserSegment.objects.select_related("segment", "assigned_by").filter(user=user)
    if include_closed is False:
        qs = qs.filter(is_active=True, end_date__isnull=True)
    qs = qs.order_by("-start_date")
    rows = [serialize_assignment(r) for r in qs]
    return {"count": len(rows), "results": rows}


def create_assignment(*, user: User, data, actor, ip) -> dict:
    segment_id = data.get("segment_id")
    if not segment_id:
        raise AuthAPIError(400, "VALIDATION_ERROR", MSG_VALIDATION, extra={"field": "segment_id"})
    try:
        segment = Segment.objects.get(pk=segment_id, is_active=True)
    except Segment.DoesNotExist as exc:
        raise AuthAPIError(400, "SEGMENT_INVALID", MSG_SEGMENT_INVALID) from exc

    start_date = _parse_dt(data.get("start_date")) or timezone.now()
    end_date = _parse_dt(data.get("end_date"))
    if end_date is not None and start_date > end_date:
        raise AuthAPIError(400, "ASSIGNMENT_DATE_INVALID", MSG_DATE_INVALID)
    position = (data.get("position") or "").strip()
    position_description = (data.get("position_description") or "").strip()

    if end_date is None:
        row = open_assignment(
            user,
            segment,
            assigned_by=actor,
            start_date=start_date,
            position=position,
            position_description=position_description,
        )
    else:
        # Saisie rétroactive déjà close : pas de clôture de l’ouverte, pas de sync.
        row = UserSegment.objects.create(
            user=user,
            segment=segment,
            assigned_by=actor,
            start_date=start_date,
            end_date=end_date,
            position=position,
            position_description=position_description,
            is_active=False,
        )
        _audit(
            action="USER_SEGMENT_CREATE",
            actor=actor,
            entity_id=row.id,
            new=serialize_assignment(row),
            ip=ip,
        )
    return serialize_assignment(row)


def patch_assignment(*, row: UserSegment, data, actor, ip) -> dict:
    if "user_id" in data:
        raise AuthAPIError(400, "FIELD_FORBIDDEN", MSG_USER_ID_FROZEN)
    allowed = {
        "segment_id", "start_date", "end_date", "position", "position_description", "is_active"
    }
    if not data:
        raise AuthAPIError(400, "VALIDATION_ERROR", "Aucun champ à modifier.")
    if set(data.keys()) - allowed:
        raise AuthAPIError(400, "VALIDATION_ERROR", "Champ inconnu.")

    old = serialize_assignment(row)
    was_open = row.is_active and row.end_date is None
    update = []

    if "segment_id" in data:
        try:
            segment = Segment.objects.get(pk=data["segment_id"], is_active=True)
        except Segment.DoesNotExist as exc:
            raise AuthAPIError(400, "SEGMENT_INVALID", MSG_SEGMENT_INVALID) from exc
        row.segment = segment
        update.append("segment")

    if "start_date" in data:
        parsed = _parse_dt(data.get("start_date"))
        if parsed is not None:
            row.start_date = parsed
        update.append("start_date")

    if "end_date" in data:
        row.end_date = _parse_dt(data.get("end_date"))
        update.append("end_date")

    if row.end_date is not None and row.start_date > row.end_date:
        raise AuthAPIError(400, "ASSIGNMENT_DATE_INVALID", MSG_DATE_INVALID)

    if "position" in data:
        row.position = (data.get("position") or "").strip()
        update.append("position")

    if "position_description" in data:
        row.position_description = (data.get("position_description") or "").strip()
        update.append("position_description")

    if "is_active" in data:
        row.is_active = bool(data.get("is_active"))
        update.append("is_active")

    if not update:
        raise AuthAPIError(400, "VALIDATION_ERROR", "Aucun champ à modifier.")

    update.append("updated_at")
    row.save(update_fields=update)
    sync_users_segment_id(row.user)

    now_open = row.is_active and row.end_date is None
    action = "USER_SEGMENT_CLOSE" if (was_open and not now_open) else "USER_SEGMENT_UPDATE"
    new = serialize_assignment(row)
    _audit(action=action, actor=actor, entity_id=row.id, old=old, new=new, ip=ip)
    return new


def delete_assignment(*, row: UserSegment, actor, ip) -> None:
    old = serialize_assignment(row)
    row_id = row.id
    user = row.user
    row.delete()
    sync_users_segment_id(user)
    _audit(action="USER_SEGMENT_DELETE", actor=actor, entity_id=row_id, old=old, ip=ip)
