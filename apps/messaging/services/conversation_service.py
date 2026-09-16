"""MESSAGERIE-A : inbox, création/réouverture fil privé, détail, archive, pin, mute, épinglés."""

from django.db import transaction
from django.db.models import Q

from apps.iam.exceptions import AuthAPIError
from apps.iam.models import User
from apps.media.services.avatar_service import avatar_url
from apps.messaging.models import (
    ArchivedConversation,
    BlockedUser,
    Conversation,
    ConversationMember,
    ConversationSetting,
    PinnedMessage,
)

MSG_NOT_FOUND = "Conversation introuvable."
MSG_USER_NOT_FOUND = "Utilisateur introuvable."
MSG_VALIDATION = "Paramètre invalide."
MSG_USER_BLOCKED = "Vous ne pouvez pas contacter cet utilisateur."

_INBOX_LIMIT_MAX = 50


def get_member_or_404(user, *, conversation_id=None, conversation_uuid=None) -> ConversationMember:
    qs = ConversationMember.objects.select_related("conversation").filter(user=user, active=True)
    try:
        if conversation_id is not None:
            return qs.get(conversation_id=conversation_id)
        return qs.get(conversation__conversation_uuid=conversation_uuid)
    except ConversationMember.DoesNotExist as exc:
        raise AuthAPIError(404, "NOT_FOUND", MSG_NOT_FOUND) from exc


def _muted(conversation, user) -> bool:
    setting = ConversationSetting.objects.filter(conversation=conversation, user=user).first()
    return bool(setting and setting.muted)


def _peer_summary(conversation, member) -> dict | None:
    if conversation.type != Conversation.Type.PRIVATE:
        return None
    peer_member = (
        ConversationMember.objects.select_related("user")
        .filter(conversation=conversation, active=True)
        .exclude(user_id=member.user_id)
        .first()
    )
    if peer_member is None:
        return None
    peer = peer_member.user
    return {
        "user_id": str(peer.id),
        "display_name": peer.get_full_name(),
        "avatar_url": avatar_url(peer),
    }


def _serialize_summary(member: ConversationMember) -> dict:
    conversation = member.conversation
    peer = _peer_summary(conversation, member)
    return {
        "id": str(conversation.id),
        "conversation_uuid": str(conversation.conversation_uuid),
        "type": conversation.type,
        "title": conversation.title,
        "encrypted": conversation.encrypted,
        "last_message_at": (
            conversation.last_message_at.isoformat() if conversation.last_message_at else None
        ),
        "unread_count": member.unread_count,
        "pinned": member.pinned,
        "archived": member.archived,
        "muted": _muted(conversation, member.user),
        "avatar_url": peer["avatar_url"] if peer else None,
        "peer_summary": peer,
    }


def list_inbox(*, user, archived=False, pinned=None, type_=None, limit=20, before=None) -> dict:
    limit = min(max(int(limit or 20), 1), _INBOX_LIMIT_MAX)
    qs = ConversationMember.objects.select_related("conversation").filter(
        user=user, active=True, archived=bool(archived)
    )
    if pinned:
        qs = qs.filter(pinned=True)
    if type_:
        qs = qs.filter(conversation__type=type_)
    if before:
        qs = qs.filter(conversation__last_message_at__lt=before)
    rows = list(qs.order_by("-conversation__last_message_at")[: limit + 1])
    next_before = None
    if len(rows) > limit:
        rows = rows[:limit]
        last_at = rows[-1].conversation.last_message_at
        next_before = last_at.isoformat() if last_at else None
    return {"results": [_serialize_summary(m) for m in rows], "next_before": next_before}


def get_detail(*, user, conversation_id=None, conversation_uuid=None) -> dict:
    member = get_member_or_404(
        user, conversation_id=conversation_id, conversation_uuid=conversation_uuid
    )
    conversation = member.conversation
    peer = _peer_summary(conversation, member)
    return {
        "id": str(conversation.id),
        "conversation_uuid": str(conversation.conversation_uuid),
        "type": conversation.type,
        "title": conversation.title,
        "description": conversation.description,
        "encrypted": conversation.encrypted,
        "avatar_url": peer["avatar_url"] if peer else None,
        "created_at": conversation.created_at.isoformat(),
        "settings": {
            "muted": _muted(conversation, user),
            "pinned": member.pinned,
            "role": member.role,
            "joined_at": member.joined_at.isoformat(),
        },
    }


def find_or_create_private(*, user, participant_id) -> tuple[dict, bool]:
    if str(participant_id) == str(user.id):
        raise AuthAPIError(
            400, "VALIDATION_ERROR", MSG_VALIDATION, extra={"field": "participant_id"}
        )
    try:
        participant = User.objects.get(pk=participant_id, is_active=True)
    except (User.DoesNotExist, ValueError, TypeError) as exc:
        raise AuthAPIError(404, "NOT_FOUND", MSG_USER_NOT_FOUND) from exc

    blocked = BlockedUser.objects.filter(
        Q(blocker=user, blocked=participant) | Q(blocker=participant, blocked=user)
    ).exists()
    if blocked:
        raise AuthAPIError(403, "USER_BLOCKED", MSG_USER_BLOCKED)

    existing = (
        ConversationMember.objects.filter(
            user=user, active=True, conversation__type=Conversation.Type.PRIVATE
        )
        .filter(conversation__members__user=participant, conversation__members__active=True)
        .select_related("conversation")
        .first()
    )
    if existing is not None:
        return get_detail(user=user, conversation_id=existing.conversation_id), False

    with transaction.atomic():
        conversation = Conversation.objects.create(
            type=Conversation.Type.PRIVATE, encrypted=True, owner=user
        )
        ConversationMember.objects.create(
            conversation=conversation, user=user, role=ConversationMember.Role.MEMBER
        )
        ConversationMember.objects.create(
            conversation=conversation, user=participant, role=ConversationMember.Role.MEMBER
        )
    return get_detail(user=user, conversation_id=conversation.id), True


def set_archived(*, user, conversation_id, archived: bool) -> dict:
    member = get_member_or_404(user, conversation_id=conversation_id)
    if archived:
        ArchivedConversation.objects.get_or_create(conversation=member.conversation, user=user)
    else:
        ArchivedConversation.objects.filter(conversation=member.conversation, user=user).delete()
    if member.archived != archived:
        member.archived = archived
        member.save(update_fields=["archived"])
    return {"archived": archived}


def set_pinned(*, user, conversation_id, pinned: bool) -> dict:
    member = get_member_or_404(user, conversation_id=conversation_id)
    if member.pinned != pinned:
        member.pinned = pinned
        member.save(update_fields=["pinned"])
    return {"pinned": pinned}


def set_muted(*, user, conversation_id, muted: bool) -> dict:
    member = get_member_or_404(user, conversation_id=conversation_id)
    ConversationSetting.objects.update_or_create(
        conversation=member.conversation, user=user, defaults={"muted": muted}
    )
    return {"muted": muted}


def list_pinned_messages(*, user, conversation_id) -> dict:
    member = get_member_or_404(user, conversation_id=conversation_id)
    rows = PinnedMessage.objects.filter(conversation=member.conversation).order_by("-pinned_at")
    return {
        "results": [
            {
                "message_id": str(row.message_id),
                "pinned_at": row.pinned_at.isoformat(),
                "pinned_by": str(row.pinned_by_id) if row.pinned_by_id else None,
            }
            for row in rows
        ]
    }
