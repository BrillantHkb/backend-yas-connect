"""AUTH-F : portes CGU puis wizard (langue / fuseau / son). Pas AUTH-39."""

import uuid

from django.conf import settings
from django.utils import timezone

from apps.iam.exceptions import AuthAPIError
from apps.iam.models import AuditLog, User

MSG_TOS_REQUIRED = "Acceptation des CGU requise."
MSG_ONBOARDING_REQUIRED = "Finalisez la configuration du compte."
MSG_TOS_MISMATCH = "Version des CGU obsolète."


def current_tos_version() -> str:
    """Version CGU en vigueur (.env). Bump → tos_ok faux, wizard inchangé."""
    return settings.YAS_TOS_VERSION


def current_tos_url() -> str:
    """URL du texte légal (pas de PDF en base)."""
    return settings.YAS_TOS_URL


def tos_ok(user: User) -> bool:
    """Accepté ET version stockée = version courante."""
    return bool(user.tos_accepted_at) and user.tos_version == current_tos_version()


def onboarding_ok(user: User) -> bool:
    """Wizard terminé (timestamp, pas un booléen first_login)."""
    return user.onboarding_completed_at is not None


def gates_payload(user: User) -> dict:
    """Fragment GET /me : le client lit ça avant d’ouvrir le métier."""
    first = user.first_login
    return {
        "tos_required": not tos_ok(user),
        "tos_current_version": current_tos_version(),
        "onboarding_required": not onboarding_ok(user),
        "first_login_at": first.isoformat() if first else None,
    }


def tos_public() -> dict:
    """GET /me/tos : version + URL courantes."""
    return {"version": current_tos_version(), "url": current_tos_url()}


def accept_tos(*, user: User, version: str) -> None:
    """AUTH-40 : version doit égaler la courante, sinon 409. Audit TOS_ACCEPT."""
    current = current_tos_version()
    if version != current:
        raise AuthAPIError(409, "TOS_VERSION_MISMATCH", MSG_TOS_MISMATCH)
    now = timezone.now()
    user.tos_accepted_at = now
    user.tos_version = version
    user.save(update_fields=["tos_accepted_at", "tos_version", "updated_at"])
    AuditLog.objects.create(
        trace_id=uuid.uuid4(),
        module="IAM",
        action="TOS_ACCEPT",
        entity_type="users",
        entity_id=user.id,
        metadata={"version": version},
        severity="INFO",
        success=True,
        user=user,
    )


def onboarding_payload(user: User) -> dict:
    """GET wizard : prérempli prefs (défauts fr / Lomé / true), jamais un formulaire vide."""
    prefs = getattr(user, "preferences", None)
    language = (prefs.language if prefs else None) or user.language or "fr"
    tz = (prefs.timezone if prefs else None) or user.timezone or "Africa/Lome"
    sound = prefs.notification_sound if prefs is not None else True
    return {
        "language": language,
        "timezone": tz,
        "notification_sound": sound,
    }


def patch_onboarding(
    *,
    user: User,
    language: str | None = None,
    timezone_name: str | None = None,
    notification_sound: bool | None = None,
) -> dict:
    """AUTH-38 : prefs + users.language/timezone. Ne pose pas onboarding_completed_at."""
    prefs = user.preferences
    user_fields = []
    if language is not None:
        user.language = language
        prefs.language = language
        user_fields.extend(["language"])
    if timezone_name is not None:
        user.timezone = timezone_name
        prefs.timezone = timezone_name
        user_fields.append("timezone")
    if notification_sound is not None:
        prefs.notification_sound = notification_sound
    if user_fields:
        user.save(update_fields=[*user_fields, "updated_at"])
    prefs.save()
    return onboarding_payload(user)


def complete_onboarding(*, user: User) -> None:
    """AUTH-42 : exige tos_ok. Idempotent si déjà posé. Audit ONBOARDING_COMPLETE."""
    if not tos_ok(user):
        raise AuthAPIError(403, "TOS_REQUIRED", MSG_TOS_REQUIRED)
    if user.onboarding_completed_at is not None:
        return  # déjà fini : pas de 2e audit
    user.onboarding_completed_at = timezone.now()
    user.save(update_fields=["onboarding_completed_at", "updated_at"])
    AuditLog.objects.create(
        trace_id=uuid.uuid4(),
        module="IAM",
        action="ONBOARDING_COMPLETE",
        entity_type="users",
        entity_id=user.id,
        severity="INFO",
        success=True,
        user=user,
    )
