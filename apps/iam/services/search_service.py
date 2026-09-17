"""ANNUAIRE-A : GET /users people-picker. Pas d’email / phone / matricule dans le hit."""

import uuid

from django.db.models import Q

from apps.annuaire.models import Segment
from apps.iam.exceptions import AuthAPIError
from apps.iam.models import User, Visibility
from apps.iam.services.presence_service import colleague_presence
from apps.iam.services.profile_service import _visible
from apps.media.services.avatar_service import avatar_url

MSG_QUERY_TOO_SHORT = "Recherche trop courte."
MSG_VALIDATION = "Paramètre invalide."

MIN_Q = 2
MAX_Q = 64
DEFAULT_LIMIT = 20
MAX_LIMIT = 50


def _parse_uuid(raw, name: str):
    if raw is None or raw == "":
        return None
    try:
        return uuid.UUID(str(raw))
    except (TypeError, ValueError) as exc:
        raise AuthAPIError(
            400, "VALIDATION_ERROR", MSG_VALIDATION, extra={"field": name}
        ) from exc


def _parse_limit_offset(params) -> tuple[int, int]:
    """Pagination offset volontaire, pas une omission : le people-picker (ANN-01)
    trie par pertinence/alphabétique sur une requête libre, pas chronologiquement
    — le curseur keyset (`before`) utilisé ailleurs (messages, notifs, inbox) n'a
    pas de sens ici. Exception documentée, pas à aligner sur le reste de l'API."""
    try:
        limit = int(params.get("limit", DEFAULT_LIMIT))
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
    if limit < 1 or limit > MAX_LIMIT:
        raise AuthAPIError(400, "VALIDATION_ERROR", MSG_VALIDATION, extra={"field": "limit"})
    if offset < 0:
        raise AuthAPIError(400, "VALIDATION_ERROR", MSG_VALIDATION, extra={"field": "offset"})
    return limit, offset


def _org_mini(user: User, segments_by_id: dict) -> dict | None:
    if not user.segment_id:
        return None
    segment = segments_by_id.get(user.segment_id)
    if segment is None:
        return None
    return {"segment": {"id": str(segment.id), "code": segment.code, "name": segment.name}}


def _hit(user: User, *, viewer: User, segments_by_id: dict) -> dict:
    privacy = getattr(user, "privacy", None)
    photo_vis = privacy.profile_photo_visibility if privacy else Visibility.EVERYONE
    show_photo = _visible(photo_vis, viewer, user)
    presence = colleague_presence(target=user, viewer=viewer)
    return {
        "id": str(user.id),
        "display_name": user.get_full_name(),
        "username": user.username,
        "job_title": user.job_title,
        "avatar_url": avatar_url(user) if show_photo else None,
        "org": _org_mini(user, segments_by_id),
        "status": presence["status"],
        "badge": presence["badge"],
    }


def search_users(*, request, viewer: User) -> dict:
    """ANN-01 : q obligatoire 2–64, actifs non pending, pas soi, pas d’e-mail."""
    params = request.query_params
    q = (params.get("q") or "").strip()
    if len(q) < MIN_Q or len(q) > MAX_Q:
        raise AuthAPIError(400, "QUERY_TOO_SHORT", MSG_QUERY_TOO_SHORT)

    qs = (
        User.objects.select_related("privacy")
        .filter(is_active=True, pending_approval=False)
        .exclude(pk=viewer.pk)
        .filter(
            Q(first_name__icontains=q)
            | Q(last_name__icontains=q)
            | Q(username__icontains=q)
            | Q(matricule__icontains=q)
        )
    )

    region_id = _parse_uuid(params.get("region_id"), "region_id")
    if region_id is not None:
        qs = qs.filter(region_id=region_id)
    segment_id = _parse_uuid(params.get("segment_id"), "segment_id")
    if segment_id is not None:
        qs = qs.filter(segment_id=segment_id)

    limit, offset = _parse_limit_offset(params)
    qs = qs.order_by("last_name", "first_name", "id")
    total = qs.count()
    page = list(qs[offset : offset + limit])

    seg_ids = {u.segment_id for u in page if u.segment_id}
    segments_by_id = {s.id: s for s in Segment.objects.filter(id__in=seg_ids)} if seg_ids else {}

    results = [_hit(u, viewer=viewer, segments_by_id=segments_by_id) for u in page]
    return {"count": total, "results": results}
