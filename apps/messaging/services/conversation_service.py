"""MESSAGERIE-A/C : inbox, conversations privées/groupes, membres, réglages."""

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.crypto.services.key_service import ensure_conversation_key
from apps.iam.exceptions import AuthAPIError
from apps.iam.models import PrivacySetting, User
from apps.media.services.avatar_service import avatar_url
from apps.media.services.upload_service import get_own_media_or_404
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
MSG_FORBIDDEN = "Action non autorisée sur ce groupe."
MSG_ALREADY_MEMBER = "Déjà membre actif de ce groupe."
MSG_INVITE_REFUSED = "Cet utilisateur n'accepte pas les invitations de groupe."
MSG_GROUP_FULL = "Ce groupe a atteint son nombre maximal de membres."
MSG_OWNER_MUST_TRANSFER = "Transférez la propriété avant de quitter/retirer l'OWNER."

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


# --- MSG-41 : créer un groupe -----------------------------------------------------


def create_group(*, user, title, member_ids, visibility="PRIVATE") -> dict:
    title = (title or "").strip()
    valid_members = []
    seen = {str(user.id)}
    for raw_id in member_ids or []:
        uid = str(raw_id)
        if uid in seen:
            continue
        seen.add(uid)
        try:
            candidate = User.objects.get(pk=uid, is_active=True)
        except (User.DoesNotExist, ValueError, TypeError):
            continue
        privacy, _ = PrivacySetting.objects.get_or_create(user=candidate)
        if not privacy.allow_group_invites:
            continue
        blocked = BlockedUser.objects.filter(
            Q(blocker=user, blocked=candidate) | Q(blocker=candidate, blocked=user)
        ).exists()
        if blocked:
            continue
        valid_members.append(candidate)

    if not valid_members:
        raise AuthAPIError(400, "VALIDATION_ERROR", MSG_VALIDATION, extra={"field": "member_ids"})

    with transaction.atomic():
        conversation = Conversation.objects.create(
            type=Conversation.Type.GROUP, title=title, encrypted=False, owner=user
        )
        ConversationMember.objects.create(
            conversation=conversation, user=user, role=ConversationMember.Role.OWNER
        )
        for candidate in valid_members:
            ConversationMember.objects.create(
                conversation=conversation, user=candidate, role=ConversationMember.Role.MEMBER
            )
        ConversationSetting.objects.update_or_create(
            conversation=conversation,
            user=user,
            defaults={"visibility": visibility or ConversationSetting.Visibility.PRIVATE},
        )
        ensure_conversation_key(conversation.id)

    return get_detail(user=user, conversation_id=conversation.id), True


def _owner_member(conversation) -> ConversationMember:
    owner = (
        ConversationMember.objects.filter(
            conversation=conversation, role=ConversationMember.Role.OWNER, active=True
        )
        .select_related("user")
        .first()
    )
    if owner is None:
        raise AuthAPIError(404, "NOT_FOUND", MSG_NOT_FOUND)
    return owner


# --- MSG-42/43 : métadonnées groupe ------------------------------------------------


def update_conversation(*, user, conversation_id, data: dict) -> dict:
    member = get_member_or_404(user, conversation_id=conversation_id)
    conversation = member.conversation
    if conversation.type != Conversation.Type.GROUP:
        raise AuthAPIError(400, "VALIDATION_ERROR", MSG_VALIDATION, extra={"field": "type"})
    if member.role not in (ConversationMember.Role.OWNER, ConversationMember.Role.ADMIN):
        raise AuthAPIError(403, "FORBIDDEN", MSG_FORBIDDEN)

    fields = []
    if "title" in data:
        conversation.title = data["title"].strip()
        fields.append("title")
    if "description" in data:
        conversation.description = data["description"]
        fields.append("description")
    if "avatar_media_id" in data:
        avatar_id = data["avatar_media_id"]
        conversation.avatar_media = get_own_media_or_404(user, avatar_id) if avatar_id else None
        fields.append("avatar_media")
    if fields:
        fields.append("updated_at")
        conversation.save(update_fields=fields)
    return get_detail(user=user, conversation_id=conversation.id)


# --- group-settings : visibilité, locked, max_members, accueil, règles ------------


def update_group_settings(*, user, conversation_id, data: dict) -> dict:
    member = get_member_or_404(user, conversation_id=conversation_id)
    conversation = member.conversation
    if conversation.type != Conversation.Type.GROUP:
        raise AuthAPIError(400, "VALIDATION_ERROR", MSG_VALIDATION, extra={"field": "type"})
    if member.role not in (ConversationMember.Role.OWNER, ConversationMember.Role.ADMIN):
        raise AuthAPIError(403, "FORBIDDEN", MSG_FORBIDDEN)

    owner_member = _owner_member(conversation)
    setting, _ = ConversationSetting.objects.get_or_create(
        conversation=conversation, user=owner_member.user
    )
    if "visibility" in data:
        setting.visibility = data["visibility"]
    if "locked" in data:
        setting.locked = data["locked"]
    if "max_members" in data:
        setting.max_members = data["max_members"]
    custom = dict(setting.custom_settings or {})
    if "welcome_message" in data:
        custom["welcome_message"] = data["welcome_message"]
    if "rules" in data:
        custom["rules"] = data["rules"]
    setting.custom_settings = custom
    setting.save(update_fields=["visibility", "locked", "max_members", "custom_settings"])
    return {
        "visibility": setting.visibility,
        "locked": setting.locked,
        "max_members": setting.max_members,
        "welcome_message": custom.get("welcome_message", ""),
        "rules": custom.get("rules", ""),
    }


# --- MSG-44 : membres --------------------------------------------------------------


def list_members(*, user, conversation_id, active=True) -> dict:
    member = get_member_or_404(user, conversation_id=conversation_id)
    qs = ConversationMember.objects.filter(conversation=member.conversation)
    if active:
        qs = qs.filter(active=True)
    qs = qs.select_related("user").order_by("joined_at")
    return {
        "results": [
            {
                "user_id": str(m.user_id),
                "username": m.username,
                "role": m.role,
                "joined_at": m.joined_at.isoformat(),
                "left_at": m.left_at.isoformat() if m.left_at else None,
            }
            for m in qs
        ]
    }


def add_member(*, user, conversation_id, target_user_id, role="MEMBER") -> dict:
    member = get_member_or_404(user, conversation_id=conversation_id)
    conversation = member.conversation
    if conversation.type != Conversation.Type.GROUP:
        raise AuthAPIError(400, "VALIDATION_ERROR", MSG_VALIDATION, extra={"field": "type"})
    if member.role not in (ConversationMember.Role.OWNER, ConversationMember.Role.ADMIN):
        raise AuthAPIError(403, "FORBIDDEN", MSG_FORBIDDEN)

    try:
        target = User.objects.get(pk=target_user_id, is_active=True)
    except (User.DoesNotExist, ValueError, TypeError) as exc:
        raise AuthAPIError(404, "NOT_FOUND", MSG_USER_NOT_FOUND) from exc

    existing = ConversationMember.objects.filter(conversation=conversation, user=target).first()
    if existing is not None and existing.active:
        raise AuthAPIError(409, "ALREADY_MEMBER", MSG_ALREADY_MEMBER)

    privacy, _ = PrivacySetting.objects.get_or_create(user=target)
    if not privacy.allow_group_invites:
        raise AuthAPIError(403, "INVITE_REFUSED", MSG_INVITE_REFUSED)
    blocked = BlockedUser.objects.filter(
        Q(blocker=user, blocked=target) | Q(blocker=target, blocked=user)
    ).exists()
    if blocked:
        raise AuthAPIError(403, "USER_BLOCKED", MSG_USER_BLOCKED)

    owner_member = _owner_member(conversation)
    setting = ConversationSetting.objects.filter(
        conversation=conversation, user=owner_member.user
    ).first()
    if setting and setting.max_members:
        current_count = ConversationMember.objects.filter(
            conversation=conversation, active=True
        ).count()
        if current_count >= setting.max_members:
            raise AuthAPIError(409, "GROUP_FULL", MSG_GROUP_FULL)

    if existing is not None:
        existing.active = True
        existing.left_at = None
        existing.role = role
        existing.save(update_fields=["active", "left_at", "role"])
        row = existing
    else:
        row = ConversationMember.objects.create(conversation=conversation, user=target, role=role)
    return {"user_id": str(target.id), "role": row.role, "joined_at": row.joined_at.isoformat()}


def update_member(*, user, conversation_id, target_user_id, data: dict) -> dict:
    member = get_member_or_404(user, conversation_id=conversation_id)
    conversation = member.conversation
    if conversation.type != Conversation.Type.GROUP:
        raise AuthAPIError(400, "VALIDATION_ERROR", MSG_VALIDATION, extra={"field": "type"})

    try:
        target_member = ConversationMember.objects.select_related("user").get(
            conversation=conversation, user_id=target_user_id, active=True
        )
    except ConversationMember.DoesNotExist as exc:
        raise AuthAPIError(404, "NOT_FOUND", MSG_NOT_FOUND) from exc

    new_role = data.get("role")
    if new_role:
        if new_role == ConversationMember.Role.OWNER:
            if member.role != ConversationMember.Role.OWNER:
                raise AuthAPIError(403, "FORBIDDEN", MSG_FORBIDDEN)
            if target_member.user_id != member.user_id:
                with transaction.atomic():
                    member.role = ConversationMember.Role.ADMIN
                    member.save(update_fields=["role"])
                    target_member.role = ConversationMember.Role.OWNER
                    target_member.save(update_fields=["role"])
        else:
            if member.role == ConversationMember.Role.ADMIN and target_member.role in (
                ConversationMember.Role.OWNER,
                ConversationMember.Role.ADMIN,
            ):
                raise AuthAPIError(403, "FORBIDDEN", MSG_FORBIDDEN)
            if member.role not in (ConversationMember.Role.OWNER, ConversationMember.Role.ADMIN):
                raise AuthAPIError(403, "FORBIDDEN", MSG_FORBIDDEN)
            target_member.role = new_role
            target_member.save(update_fields=["role"])

    if "username" in data:
        is_self = target_member.user_id == user.id
        is_privileged = member.role in (
            ConversationMember.Role.OWNER,
            ConversationMember.Role.ADMIN,
        )
        if not is_self and not is_privileged:
            raise AuthAPIError(403, "FORBIDDEN", MSG_FORBIDDEN)
        target_member.username = data["username"]
        target_member.save(update_fields=["username"])

    return {
        "user_id": str(target_member.user_id),
        "role": target_member.role,
        "username": target_member.username,
    }


def remove_member(*, user, conversation_id, target_user_id) -> dict:
    member = get_member_or_404(user, conversation_id=conversation_id)
    conversation = member.conversation
    if conversation.type != Conversation.Type.GROUP:
        raise AuthAPIError(400, "VALIDATION_ERROR", MSG_VALIDATION, extra={"field": "type"})
    if member.role not in (ConversationMember.Role.OWNER, ConversationMember.Role.ADMIN):
        raise AuthAPIError(403, "FORBIDDEN", MSG_FORBIDDEN)

    try:
        target_member = ConversationMember.objects.get(
            conversation=conversation, user_id=target_user_id, active=True
        )
    except ConversationMember.DoesNotExist as exc:
        raise AuthAPIError(404, "NOT_FOUND", MSG_NOT_FOUND) from exc

    if target_member.role == ConversationMember.Role.OWNER:
        raise AuthAPIError(403, "OWNER_MUST_TRANSFER", MSG_OWNER_MUST_TRANSFER)
    both_admin = (
        member.role == ConversationMember.Role.ADMIN
        and target_member.role == ConversationMember.Role.ADMIN
    )
    if both_admin:
        raise AuthAPIError(403, "FORBIDDEN", MSG_FORBIDDEN)

    target_member.active = False
    target_member.left_at = timezone.now()
    target_member.save(update_fields=["active", "left_at"])
    return {"removed": True}


def leave_conversation(*, user, conversation_id) -> dict:
    member = get_member_or_404(user, conversation_id=conversation_id)
    if member.role == ConversationMember.Role.OWNER:
        raise AuthAPIError(403, "OWNER_MUST_TRANSFER", MSG_OWNER_MUST_TRANSFER)
    member.active = False
    member.left_at = timezone.now()
    member.save(update_fields=["active", "left_at"])
    return {"left": True}


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
