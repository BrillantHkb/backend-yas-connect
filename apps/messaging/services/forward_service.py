"""MESSAGERIE-E : transfert de message entre fils (MSG-75/76)."""

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.crypto.services import wrapping
from apps.iam.exceptions import AuthAPIError
from apps.messaging.models import (
    Conversation,
    ConversationMember,
    ConversationSetting,
    Message,
    MessageForward,
)
from apps.messaging.services import conversation_service, message_service, realtime_service

MSG_NOT_FOUND = "Message introuvable."
MSG_CONTENT_REQUIRED = "encrypted_content requis pour transférer vers/depuis un fil privé."
MSG_CONVERSATION_LOCKED = "Ce fil est verrouillé."
MSG_READ_ONLY_MEMBER = "Vous êtes en lecture seule sur ce fil."


def forward_message(*, user, message_id, target_conversation_id, encrypted_content_b64="") -> dict:
    try:
        original = Message.objects.select_related("conversation").get(pk=message_id)
    except (Message.DoesNotExist, ValueError, TypeError) as exc:
        raise AuthAPIError(404, "NOT_FOUND", MSG_NOT_FOUND) from exc
    conversation_service.get_member_or_404(user, conversation_id=original.conversation_id)
    target_member = conversation_service.get_member_or_404(
        user, conversation_id=target_conversation_id
    )
    target = target_member.conversation

    source_group_key = message_service.resolve_group_key(original.conversation)
    target_group_key = message_service.resolve_group_key(target)

    if encrypted_content_b64:
        content_bytes = message_service.decode_b64(encrypted_content_b64, "encrypted_content")
        if target_group_key is not None:
            content_bytes = wrapping.wrap_with_key(target_group_key, content_bytes)
    else:
        both_group = (
            original.conversation.type == Conversation.Type.GROUP
            and target.type == Conversation.Type.GROUP
        )
        if not both_group:
            raise AuthAPIError(
                400, "VALIDATION_ERROR", MSG_CONTENT_REQUIRED, extra={"field": "encrypted_content"}
            )
        raw = bytes(original.encrypted_content or b"")
        plaintext = wrapping.unwrap_with_key(source_group_key, raw) if raw else b""
        content_bytes = wrapping.wrap_with_key(target_group_key, plaintext) if plaintext else b""

    owner_member = ConversationMember.objects.filter(
        conversation=target, role=ConversationMember.Role.OWNER, active=True
    ).first()
    locked = False
    if owner_member is not None:
        setting = ConversationSetting.objects.filter(
            conversation=target, user=owner_member.user
        ).first()
        locked = bool(setting and setting.locked)
    privileged = (ConversationMember.Role.OWNER, ConversationMember.Role.ADMIN)
    if locked and target_member.role not in privileged:
        raise AuthAPIError(403, "CONVERSATION_LOCKED", MSG_CONVERSATION_LOCKED)
    if target_member.role == ConversationMember.Role.READ_ONLY:
        raise AuthAPIError(403, "READ_ONLY_MEMBER", MSG_READ_ONLY_MEMBER)

    others = ConversationMember.objects.filter(conversation=target, active=True).exclude(
        user_id=user.id
    )
    with transaction.atomic():
        new_message = Message.objects.create(
            type=original.type,
            encrypted_content=content_bytes,
            conversation=target,
            sender=user,
            forwarded=True,
            sent_at=timezone.now(),
        )
        MessageForward.objects.create(
            original_message=original, new_message=new_message, forwarded_by=user
        )
        others.update(unread_count=F("unread_count") + 1)
        target.last_message = new_message
        target.last_message_at = new_message.sent_at
        target.save(update_fields=["last_message", "last_message_at", "updated_at"])

    serialized = message_service.serialize_message(new_message, target_group_key)
    realtime_service.broadcast_message_created(target.id, serialized)
    return serialized
