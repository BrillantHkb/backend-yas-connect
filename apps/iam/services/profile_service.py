"""PROF-A : fiche /me, PATCH, fiche collègue, privacy, email_pending."""

import re
import uuid

from django.db.models import Q
from django.utils import timezone

from apps.iam.exceptions import AuthAPIError
from apps.iam.models import AuditLog, EmailVerification, User, Visibility
from apps.iam.services.org_resolver import resolve_org
from apps.iam.services.prefs_service import job_title_self_edit
from apps.media.services.avatar_service import avatar_url

MSG_FIELD = "Champ interdit."
MSG_USERNAME = "Ce nom d’utilisateur est déjà pris."
MSG_USE_ME = "Utiliser GET /me."
MSG_NOT_FOUND = "Utilisateur introuvable."
MSG_PATCH_EMPTY = "Aucun champ à modifier."

ALLOWED_PATCH = frozenset({"first_name", "last_name", "username", "phone"})
USERNAME_RE = re.compile(r"^[a-z0-9._]+$")
PHONE_RE = re.compile(r"^\+[1-9]\d{6,14}$")


def _iso(dt):
    return dt.isoformat() if dt else None


def _prefs(user) -> dict | None:
    prefs = getattr(user, "preferences", None)
    if prefs is None:
        return None
    return {
        "language": prefs.language,
        "timezone": prefs.timezone,
        "notification_sound": prefs.notification_sound,
        "auto_download_media": prefs.auto_download_media,
        "read_receipts": prefs.read_receipts,
        "typing_indicator": prefs.typing_indicator,
    }


def _privacy(user) -> dict | None:
    privacy = getattr(user, "privacy", None)
    if privacy is None:
        return None
    return {
        "last_seen_visibility": privacy.last_seen_visibility,
        "profile_photo_visibility": privacy.profile_photo_visibility,
        "online_status_visibility": privacy.online_status_visibility,
        "read_receipts_enabled": privacy.read_receipts_enabled,
        "typing_indicator_enabled": privacy.typing_indicator_enabled,
        "allow_calls": privacy.allow_calls,
        "allow_mentions": privacy.allow_mentions,
        "allow_group_invites": privacy.allow_group_invites,
    }


def _region(user) -> dict | None:
    region = getattr(user, "region", None)
    if region is None:
        return None
    return {"id": str(region.id), "code": region.code, "name": region.name}


def email_pending(user: User) -> str | None:
    now = timezone.now()
    row = (
        EmailVerification.objects.filter(
            user=user,
            purpose=EmailVerification.Purpose.EMAIL_CHANGE,
            verified_at__isnull=True,
            revoked_at__isnull=True,
            expires_at__gt=now,
        )
        .order_by("-created_at")
        .first()
    )
    return row.email if row else None


def _is_contact(viewer: User, target: User) -> bool:
    return (
        viewer.segment_id is not None
        and target.segment_id is not None
        and viewer.segment_id == target.segment_id
    )


def _visible(setting: str, viewer: User, target: User) -> bool:
    if setting == Visibility.EVERYONE:
        return True
    if setting == Visibility.NOBODY:
        return False
    return _is_contact(viewer, target)


def _editable() -> dict:
    return {
        "first_name": True,
        "last_name": True,
        "username": True,
        "phone": True,
        "matricule": False,
        "job_title": job_title_self_edit(),
    }


def serialize_me(user: User) -> dict:
    """GET /me : pas de rôle (claim JWT). Prefs / privacy / email_pending / editable."""
    return {
        "id": str(user.id),
        "display_name": user.get_full_name(),
        "first_name": user.first_name,
        "last_name": user.last_name,
        "username": user.username,
        "email": user.email,
        "email_pending": email_pending(user),
        "phone": user.phone,
        "matricule": user.matricule,
        "job_title": user.job_title,
        "status": user.status,
        "language": user.language,
        "timezone": user.timezone,
        "segment_id": str(user.segment_id) if user.segment_id else None,
        "avatar_id": str(user.avatar_id) if user.avatar_id else None,
        "avatar_url": avatar_url(user),
        "region": _region(user),
        "org": resolve_org(user),
        "last_seen": _iso(user.last_login),
        "preferences": _prefs(user),
        "privacy": _privacy(user),
        "editable": _editable(),
    }


def serialize_colleague(*, target: User, viewer: User) -> dict:
    """GET /users/{id} : privacy du cible. Pas de gates / email_pending / prefs."""
    privacy = getattr(target, "privacy", None)
    photo_vis = privacy.profile_photo_visibility if privacy else Visibility.EVERYONE
    seen_vis = privacy.last_seen_visibility if privacy else Visibility.EVERYONE
    status_vis = privacy.online_status_visibility if privacy else Visibility.EVERYONE
    show_photo = _visible(photo_vis, viewer, target)
    show_seen = _visible(seen_vis, viewer, target)
    show_status = _visible(status_vis, viewer, target)
    role = target.role
    url = avatar_url(target) if show_photo else None
    avatar_id = str(target.avatar_id) if show_photo and target.avatar_id else None
    return {
        "id": str(target.id),
        "display_name": target.get_full_name(),
        "first_name": target.first_name,
        "last_name": target.last_name,
        "username": target.username,
        "email": target.email,
        "phone": target.phone,
        "matricule": target.matricule,
        "job_title": target.job_title,
        "status": target.status if show_status else None,
        "language": target.language,
        "timezone": target.timezone,
        "segment_id": str(target.segment_id) if target.segment_id else None,
        "avatar_id": avatar_id,
        "avatar_url": url,
        "region": _region(target),
        "org": resolve_org(target),
        "last_seen": _iso(target.last_login) if show_seen else None,
        "role": {"code": role.code, "name": role.name},
    }


def _audit(*, action, actor, entity_id, old=None, new=None, ip=None):
    AuditLog.objects.create(
        trace_id=uuid.uuid4(),
        module="IAM",
        action=action,
        entity_type="users",
        entity_id=entity_id,
        old_values=old,
        new_values=new,
        ip_address=ip,
        severity="INFO",
        success=True,
        user=actor,
    )


def patch_profile(*, user: User, data, actor, ip) -> User:
    if data is None:
        raise AuthAPIError(400, "VALIDATION_ERROR", MSG_PATCH_EMPTY)
    raw_keys = set(data.keys())
    if not raw_keys:
        raise AuthAPIError(400, "VALIDATION_ERROR", MSG_PATCH_EMPTY)
    allow_job = job_title_self_edit()
    if "job_title" in raw_keys and not allow_job:
        raise AuthAPIError(400, "FIELD_FORBIDDEN", MSG_FIELD, extra={"field": "job_title"})
    allowed = set(ALLOWED_PATCH)
    if allow_job:
        allowed.add("job_title")
    if raw_keys - allowed:
        raise AuthAPIError(400, "FIELD_FORBIDDEN", MSG_FIELD)

    old = {}
    new = {}
    update = []

    if "first_name" in data:
        value = data.get("first_name")
        if value is None or not isinstance(value, str):
            raise AuthAPIError(400, "VALIDATION_ERROR", "Prénom invalide.")
        value = value.strip()
        if len(value) > 128:
            raise AuthAPIError(400, "VALIDATION_ERROR", "Prénom invalide.")
        old["first_name"] = user.first_name
        user.first_name = value
        new["first_name"] = value
        update.append("first_name")

    if "last_name" in data:
        value = data.get("last_name")
        if value is None or not isinstance(value, str):
            raise AuthAPIError(400, "VALIDATION_ERROR", "Nom invalide.")
        value = value.strip()
        if len(value) > 128:
            raise AuthAPIError(400, "VALIDATION_ERROR", "Nom invalide.")
        old["last_name"] = user.last_name
        user.last_name = value
        new["last_name"] = value
        update.append("last_name")

    if "username" in data:
        value = data.get("username")
        if not isinstance(value, str):
            raise AuthAPIError(400, "VALIDATION_ERROR", "Nom d’utilisateur invalide.")
        value = value.strip().lower()
        if len(value) < 3 or len(value) > 64 or not USERNAME_RE.fullmatch(value):
            raise AuthAPIError(400, "VALIDATION_ERROR", "Nom d’utilisateur invalide.")
        taken = (
            User.objects.filter(Q(username=value) | Q(email=value))
            .exclude(pk=user.pk)
            .exists()
        )
        if taken:
            raise AuthAPIError(409, "USERNAME_TAKEN", MSG_USERNAME)
        old["username"] = user.username
        user.username = value
        new["username"] = value
        update.append("username")

    if "phone" in data:
        value = data.get("phone")
        if value == "":
            value = None
        if value is not None:
            if not isinstance(value, str) or not PHONE_RE.fullmatch(value):
                raise AuthAPIError(400, "VALIDATION_ERROR", "Téléphone invalide.")
        old["phone"] = user.phone
        user.phone = value
        new["phone"] = value
        update.append("phone")

    if "job_title" in data:
        value = data.get("job_title")
        if value is None:
            value = ""
        if not isinstance(value, str):
            raise AuthAPIError(400, "VALIDATION_ERROR", "Intitulé de poste invalide.")
        value = value.strip()
        if len(value) > 128:
            raise AuthAPIError(400, "VALIDATION_ERROR", "Intitulé de poste invalide.")
        old["job_title"] = user.job_title
        user.job_title = value
        new["job_title"] = value
        update.append("job_title")

    if not update:
        raise AuthAPIError(400, "VALIDATION_ERROR", MSG_PATCH_EMPTY)

    update.append("updated_at")
    user.save(update_fields=update)
    _audit(action="PROFILE_PATCH", actor=actor, entity_id=user.id, old=old, new=new, ip=ip)
    return user


def get_colleague(*, pk, viewer: User) -> User:
    if str(pk) == str(viewer.id):
        raise AuthAPIError(400, "USE_ME", MSG_USE_ME)
    try:
        target = User.objects.select_related("role", "region", "preferences", "privacy").get(pk=pk)
    except User.DoesNotExist as exc:
        raise AuthAPIError(404, "NOT_FOUND", MSG_NOT_FOUND) from exc
    if not target.is_active or target.pending_approval:
        raise AuthAPIError(404, "NOT_FOUND", MSG_NOT_FOUND)
    return target
