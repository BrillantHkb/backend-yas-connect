"""MESSAGERIE-E : signets (MSG-79/80)."""

from apps.iam.exceptions import AuthAPIError
from apps.messaging.models import ConversationMember, Message, MessageBookmark
from apps.messaging.services import conversation_service

MSG_NOT_FOUND = "Message introuvable."

_LIST_LIMIT_MAX = 50


def _get_message_and_member(user, pk):
    try:
        message = Message.objects.get(pk=pk)
    except (Message.DoesNotExist, ValueError, TypeError) as exc:
        raise AuthAPIError(404, "NOT_FOUND", MSG_NOT_FOUND) from exc
    member = conversation_service.get_member_or_404(user, conversation_id=message.conversation_id)
    return message, member


def add_bookmark(*, user, pk, note: str = "") -> dict:
    message, _member = _get_message_and_member(user, pk)
    row, _ = MessageBookmark.objects.update_or_create(
        user=user, message=message, defaults={"note": note or ""}
    )
    return {"message_id": str(message.id), "note": row.note}


def remove_bookmark(*, user, pk) -> dict:
    message, _member = _get_message_and_member(user, pk)
    MessageBookmark.objects.filter(user=user, message=message).delete()
    return {"removed": True}


def list_bookmarks(*, user, before=None, limit=20) -> dict:
    limit = min(max(int(limit or 20), 1), _LIST_LIMIT_MAX)
    active_conversation_ids = ConversationMember.objects.filter(
        user=user, active=True
    ).values_list("conversation_id", flat=True)
    qs = MessageBookmark.objects.filter(
        user=user, message__conversation_id__in=active_conversation_ids
    ).select_related("message")
    if before:
        qs = qs.filter(created_at__lt=before)
    rows = list(qs.order_by("-created_at")[: limit + 1])
    next_before = None
    if len(rows) > limit:
        rows = rows[:limit]
        next_before = rows[-1].created_at.isoformat()
    return {
        "results": [
            {
                "message_id": str(r.message_id),
                "conversation_id": str(r.message.conversation_id),
                "note": r.note,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ],
        "next_before": next_before,
    }
