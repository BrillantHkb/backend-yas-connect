"""MESSAGERIE-E : sondages GROUP (MSG-81/82/83) — création via l'envoi de message."""

from django.db import transaction
from django.utils import timezone

from apps.iam.exceptions import AuthAPIError
from apps.messaging.models import (
    Conversation,
    ConversationMember,
    Message,
    MessagePoll,
    PollOption,
    PollVote,
)
from apps.messaging.services import conversation_service

MSG_VALIDATION = "Paramètre invalide."
MSG_NOT_FOUND = "Sondage introuvable."
MSG_POLL_PRIVATE_FORBIDDEN = "Les sondages ne sont possibles que dans un groupe."
MSG_POLL_CLOSED = "Ce sondage est clos."
MSG_FORBIDDEN = "Action non autorisée sur ce sondage."

_MIN_OPTIONS = 2
_MAX_OPTIONS = 20


def serialize_poll(poll: MessagePoll) -> dict:
    return {
        "id": str(poll.id),
        "question": poll.question,
        "multiple_choices": poll.multiple_choices,
        "closed_at": poll.closed_at.isoformat() if poll.closed_at else None,
        "options": [
            {"id": str(o.id), "label": o.label, "vote_count": o.vote_count}
            for o in poll.options.order_by("created_at")
        ],
    }


def validate_poll_payload(*, conversation, data: dict) -> None:
    """Appelé par message_service.send_message avant toute écriture."""
    if conversation.type != Conversation.Type.GROUP:
        raise AuthAPIError(400, "POLL_PRIVATE_FORBIDDEN", MSG_POLL_PRIVATE_FORBIDDEN)
    if data.get("encrypted_content"):
        raise AuthAPIError(
            400, "VALIDATION_ERROR", MSG_VALIDATION, extra={"field": "encrypted_content"}
        )
    poll_data = data.get("poll") or {}
    question = (poll_data.get("question") or "").strip()
    if not question:
        raise AuthAPIError(400, "VALIDATION_ERROR", MSG_VALIDATION, extra={"field": "question"})
    options = [str(o).strip() for o in (poll_data.get("options") or []) if str(o).strip()]
    if len(options) < _MIN_OPTIONS or len(options) > _MAX_OPTIONS:
        raise AuthAPIError(400, "VALIDATION_ERROR", MSG_VALIDATION, extra={"field": "options"})


def create_poll(*, message: Message, user, device, data: dict) -> MessagePoll:
    """Appelé dans la même transaction que la création du Message (type=POLL)."""
    poll_data = data.get("poll") or {}
    question = poll_data["question"].strip()
    options = [str(o).strip() for o in poll_data.get("options") or [] if str(o).strip()]
    multiple_choices = bool(poll_data.get("multiple_choices", False))
    poll = MessagePoll.objects.create(
        message=message,
        question=question,
        multiple_choices=multiple_choices,
        device=device,
        created_by=user,
    )
    PollOption.objects.bulk_create([PollOption(poll=poll, label=label) for label in options])
    return poll


def _get_poll_and_member(user, poll_id):
    try:
        poll = MessagePoll.objects.select_related("message__conversation").get(pk=poll_id)
    except (MessagePoll.DoesNotExist, ValueError, TypeError) as exc:
        raise AuthAPIError(404, "NOT_FOUND", MSG_NOT_FOUND) from exc
    member = conversation_service.get_member_or_404(
        user, conversation_id=poll.message.conversation_id
    )
    return poll, member


def vote(*, user, poll_id, option_ids) -> dict:
    poll, _member = _get_poll_and_member(user, poll_id)
    if poll.closed_at is not None:
        raise AuthAPIError(403, "POLL_CLOSED", MSG_POLL_CLOSED)

    option_ids = [str(o) for o in (option_ids or [])]
    if not option_ids:
        raise AuthAPIError(400, "VALIDATION_ERROR", MSG_VALIDATION, extra={"field": "option_ids"})
    if not poll.multiple_choices and len(option_ids) != 1:
        raise AuthAPIError(400, "VALIDATION_ERROR", MSG_VALIDATION, extra={"field": "option_ids"})

    valid_options = list(poll.options.filter(id__in=option_ids))
    if len(valid_options) != len(set(option_ids)):
        raise AuthAPIError(400, "VALIDATION_ERROR", MSG_VALIDATION, extra={"field": "option_ids"})

    with transaction.atomic():
        PollVote.objects.filter(poll_option__poll=poll, user=user).delete()
        PollVote.objects.bulk_create(
            [PollVote(poll_option=opt, user=user) for opt in valid_options]
        )
        for opt in poll.options.all():
            opt.vote_count = opt.votes.count()
            opt.save(update_fields=["vote_count"])

    return {"option_ids": [str(o.id) for o in valid_options]}


def close_poll(*, user, poll_id) -> dict:
    poll, member = _get_poll_and_member(user, poll_id)
    is_creator = poll.created_by_id == user.id
    is_privileged = member.role in (ConversationMember.Role.OWNER, ConversationMember.Role.ADMIN)
    if not is_creator and not is_privileged:
        raise AuthAPIError(403, "FORBIDDEN", MSG_FORBIDDEN)
    if poll.closed_at is None:
        poll.closed_at = timezone.now()
        poll.save(update_fields=["closed_at"])
    return {"closed_at": poll.closed_at.isoformat()}
