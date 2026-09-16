"""MESSAGERIE-E : réactions emoji (MSG-73/74)."""

from apps.iam.exceptions import AuthAPIError
from apps.messaging.models import Message, MessageReaction
from apps.messaging.services import conversation_service, realtime_service

MSG_NOT_FOUND = "Message introuvable."
MSG_VALIDATION = "Paramètre invalide."


def _get_message_and_member(user, pk):
    try:
        message = Message.objects.get(pk=pk)
    except (Message.DoesNotExist, ValueError, TypeError) as exc:
        raise AuthAPIError(404, "NOT_FOUND", MSG_NOT_FOUND) from exc
    member = conversation_service.get_member_or_404(user, conversation_id=message.conversation_id)
    return message, member


def add_reaction(*, user, pk, emoji: str) -> dict:
    emoji = (emoji or "").strip()
    if not emoji:
        raise AuthAPIError(400, "VALIDATION_ERROR", MSG_VALIDATION, extra={"field": "emoji"})
    message, _member = _get_message_and_member(user, pk)
    MessageReaction.objects.get_or_create(message=message, user=user, emoji=emoji)
    realtime_service.broadcast_reaction_updated(message.conversation_id, message_id=message.id)
    return {"emoji": emoji, "user_id": str(user.id)}


def remove_reaction(*, user, pk, emoji: str) -> dict:
    message, _member = _get_message_and_member(user, pk)
    MessageReaction.objects.filter(message=message, user=user, emoji=emoji).delete()
    realtime_service.broadcast_reaction_updated(message.conversation_id, message_id=message.id)
    return {"removed": True}
