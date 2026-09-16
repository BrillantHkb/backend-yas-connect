"""MESSAGERIE-F : blocage utilisateur (MSG-89/90/91)."""

from apps.iam.exceptions import AuthAPIError
from apps.iam.models import User
from apps.messaging.models import BlockedUser

MSG_VALIDATION = "Paramètre invalide."
MSG_NOT_FOUND = "Utilisateur introuvable."
MSG_SELF_BLOCK = "Vous ne pouvez pas vous bloquer vous-même."
MSG_ALREADY_BLOCKED = "Cet utilisateur est déjà bloqué."


def list_blocked(*, user) -> dict:
    rows = (
        BlockedUser.objects.filter(blocker=user).select_related("blocked").order_by("-created_at")
    )
    return {
        "results": [
            {
                "user_id": str(r.blocked_id),
                "reason": r.reason,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ]
    }


def block_user(*, user, target_user_id, reason: str = "") -> dict:
    if str(target_user_id) == str(user.id):
        raise AuthAPIError(400, "VALIDATION_ERROR", MSG_SELF_BLOCK, extra={"field": "user_id"})
    try:
        target = User.objects.get(pk=target_user_id, is_active=True)
    except (User.DoesNotExist, ValueError, TypeError) as exc:
        raise AuthAPIError(404, "NOT_FOUND", MSG_NOT_FOUND) from exc
    if BlockedUser.objects.filter(blocker=user, blocked=target).exists():
        raise AuthAPIError(409, "ALREADY_BLOCKED", MSG_ALREADY_BLOCKED)
    BlockedUser.objects.create(blocker=user, blocked=target, reason=reason or "")
    return {"user_id": str(target.id), "reason": reason or ""}


def unblock_user(*, user, target_user_id) -> dict:
    BlockedUser.objects.filter(blocker=user, blocked_id=target_user_id).delete()
    return {"unblocked": True}
