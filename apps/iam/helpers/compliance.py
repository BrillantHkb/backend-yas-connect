"""Helpers AUTH-F : fermer CGU + wizard (fixtures tests, pas l’inscription)."""

from django.conf import settings
from django.utils import timezone

from apps.iam.models import User


def close_gates(user: User) -> User:
    """Pose tos_* + onboarding_completed_at = maintenant / version courante."""
    now = timezone.now()
    user.tos_accepted_at = now
    user.tos_version = settings.YAS_TOS_VERSION
    user.onboarding_completed_at = now
    user.save(
        update_fields=["tos_accepted_at", "tos_version", "onboarding_completed_at", "updated_at"]
    )
    return user
