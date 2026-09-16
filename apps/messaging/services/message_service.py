"""MESSAGERIE-B/C : historique, envoi, détail, édition, suppression, recherche."""

import base64
from datetime import timedelta

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.crypto.services import wrapping
from apps.crypto.services.key_service import (
    group_content_key,
    require_peer_ready,
    require_sender_identity,
)
from apps.iam.exceptions import AuthAPIError
from apps.iam.models import PrivacySetting
from apps.media.models import MediaFile
from apps.media.services.upload_service import get_own_media_or_404
from apps.messaging.models import (
    Conversation,
    ConversationMember,
    ConversationSetting,
    Message,
    MessageDelete,
    MessageEdit,
    MessageMention,
)
from apps.messaging.services import conversation_service, poll_service, realtime_service
from apps.notifications.models import Notification
from apps.notifications.services.notification_service import emit

MSG_NOT_FOUND = "Message introuvable."
MSG_VALIDATION = "Paramètre invalide."
MSG_CONVERSATION_LOCKED = "Ce fil est verrouillé."
MSG_READ_ONLY_MEMBER = "Vous êtes en lecture seule sur ce fil."
MSG_DUPLICATE = "Message déjà envoyé (client_message_id dupliqué)."
MSG_MEDIA_INFECTED = "Fichier joint rejeté (analyse antivirus)."
MSG_FORBIDDEN = "Action non autorisée sur ce message."
MSG_EDIT_EXPIRED = "Fenêtre d'édition expirée (15 min)."
MSG_DELETE_EXPIRED = "Fenêtre de suppression expirée (48 h)."

_EDIT_WINDOW = timedelta(minutes=15)
_DELETE_WINDOW = timedelta(hours=48)
_MESSAGES_LIMIT_MAX = 100
_SEARCH_LIMIT_MAX = 50

_ALLOWED_SEND_TYPES = frozenset(
    {
        Message.Type.TEXT,
        Message.Type.IMAGE,
        Message.Type.VIDEO,
        Message.Type.AUDIO,
        Message.Type.DOCUMENT,
    }
)
_TYPE_FROM_MEDIA = {
    MediaFile.MediaType.IMAGE: Message.Type.IMAGE,
    MediaFile.MediaType.VIDEO: Message.Type.VIDEO,
    MediaFile.MediaType.AUDIO: Message.Type.AUDIO,
    MediaFile.MediaType.DOCUMENT: Message.Type.DOCUMENT,
    MediaFile.MediaType.OTHER: Message.Type.DOCUMENT,
}


def _decode_b64(raw, field: str) -> bytes:
    if not isinstance(raw, str) or not raw:
        raise AuthAPIError(400, "VALIDATION_ERROR", MSG_VALIDATION, extra={"field": field})
    try:
        return base64.b64decode(raw, validate=True)
    except Exception as exc:
        raise AuthAPIError(400, "VALIDATION_ERROR", MSG_VALIDATION, extra={"field": field}) from exc


def _encode_b64(raw: bytes) -> str:
    return base64.b64encode(bytes(raw)).decode()


def _resolve_group_key(conversation: Conversation) -> bytes | None:
    """GROUP/AI : clé de fil serveur (CRYPTO-A). PRIVATE : None (contenu jamais touché)."""
    if conversation.type == Conversation.Type.GROUP:
        return group_content_key(conversation.id)
    return None


def _serialize_message(message: Message, group_key: bytes | None = None) -> dict:
    raw = bytes(message.encrypted_content or b"")
    if group_key is not None and raw:
        raw = wrapping.unwrap_with_key(group_key, raw)
    return {
        "id": str(message.id),
        "type": message.type,
        "encrypted_content": _encode_b64(raw),
        "sender_id": str(message.sender_id) if message.sender_id else None,
        "conversation_id": str(message.conversation_id),
        "parent_message_id": str(message.parent_message_id)
        if message.parent_message_id
        else None,
        "media_id": str(message.media_id) if message.media_id else None,
        "priority": message.priority,
        "tags": message.tags,
        "mentions": message.mentions,
        "edited": message.edited,
        "forwarded": message.forwarded,
        "pinned": message.pinned,
        "deleted": message.deleted,
        "sent_at": message.sent_at.isoformat(),
    }


def _get_message_and_member(user, pk):
    try:
        message = Message.objects.select_related("conversation").get(pk=pk)
    except (Message.DoesNotExist, ValueError, TypeError) as exc:
        raise AuthAPIError(404, "NOT_FOUND", MSG_NOT_FOUND) from exc
    member = conversation_service.get_member_or_404(user, conversation_id=message.conversation_id)
    return message, member


# Alias publics — réutilisés par forward_service.py (même app, cross-module).
resolve_group_key = _resolve_group_key
decode_b64 = _decode_b64
encode_b64 = _encode_b64
serialize_message = _serialize_message


# --- MSG-21/70 : historique + catch-up (after=) ----------------------------------


def list_messages(
    *, user, conversation_id, before=None, after=None, limit=30, parent_id=None
) -> dict:
    limit = min(max(int(limit or 30), 1), _MESSAGES_LIMIT_MAX)
    member = conversation_service.get_member_or_404(user, conversation_id=conversation_id)
    group_key = _resolve_group_key(member.conversation)
    qs = Message.objects.filter(conversation_id=conversation_id, deleted=False).exclude(
        deletes__delete_scope=MessageDelete.DeleteScope.SELF, deletes__deleted_by=user
    )
    if parent_id:
        qs = qs.filter(parent_message_id=parent_id)

    if after:
        rows = list(qs.filter(sent_at__gt=after).order_by("sent_at")[: limit + 1])
        next_after = None
        if len(rows) > limit:
            rows = rows[:limit]
            next_after = rows[-1].sent_at.isoformat()
        return {
            "results": [_serialize_message(m, group_key) for m in rows],
            "next_after": next_after,
        }

    if before:
        qs = qs.filter(sent_at__lt=before)
    rows = list(qs.order_by("-sent_at")[: limit + 1])
    next_before = None
    if len(rows) > limit:
        rows = rows[:limit]
        next_before = rows[-1].sent_at.isoformat()
    return {"results": [_serialize_message(m, group_key) for m in rows], "next_before": next_before}


# --- MSG-22 : envoyer ------------------------------------------------------------


def send_message(*, user, device, conversation_id, data: dict) -> dict:
    member = conversation_service.get_member_or_404(user, conversation_id=conversation_id)
    conversation = member.conversation
    if conversation.type not in (Conversation.Type.PRIVATE, Conversation.Type.GROUP):
        raise AuthAPIError(400, "VALIDATION_ERROR", MSG_VALIDATION, extra={"field": "type"})
    group_key = _resolve_group_key(conversation)

    # locked/visibility/max_members : toujours la ligne ConversationSetting de
    # l'OWNER qui fait foi (§0 jour 26). Pour PRIVATE il n'y a pas d'OWNER →
    # jamais verrouillable, ce qui est le comportement voulu.
    owner_member = ConversationMember.objects.filter(
        conversation=conversation, role=ConversationMember.Role.OWNER, active=True
    ).first()
    locked = False
    if owner_member is not None:
        setting = ConversationSetting.objects.filter(
            conversation=conversation, user=owner_member.user
        ).first()
        locked = bool(setting and setting.locked)
    if locked and member.role not in (ConversationMember.Role.OWNER, ConversationMember.Role.ADMIN):
        raise AuthAPIError(403, "CONVERSATION_LOCKED", MSG_CONVERSATION_LOCKED)
    if member.role == ConversationMember.Role.READ_ONLY:
        raise AuthAPIError(403, "READ_ONLY_MEMBER", MSG_READ_ONLY_MEMBER)

    client_message_id = (data.get("client_message_id") or "").strip()
    if client_message_id:
        existing = Message.objects.filter(
            conversation=conversation, sender=user, metadata__client_message_id=client_message_id
        ).first()
        if existing is not None:
            raise AuthAPIError(
                409,
                "DUPLICATE_MESSAGE",
                MSG_DUPLICATE,
                extra={"data": _serialize_message(existing, group_key)},
            )

    others = ConversationMember.objects.filter(conversation=conversation, active=True).exclude(
        user_id=user.id
    )

    msg_type = (data.get("type") or "TEXT").upper()
    is_poll = msg_type == Message.Type.POLL
    media = None
    content_bytes = b""

    if is_poll:
        poll_service.validate_poll_payload(conversation=conversation, data=data)
    else:
        if conversation.type == Conversation.Type.PRIVATE:
            require_sender_identity(device=device)
            peer_member = others.select_related("user").first()
            if peer_member is not None:
                require_peer_ready(target_user=peer_member.user)
        # GROUP : aucune garde par appareil — la confidentialité est gérée par la
        # clé de fil serveur (ensure_conversation_key), pas par Signal (§0 jour 26).

        media_id = data.get("media_id")
        if media_id:
            media = get_own_media_or_404(user, media_id)
            if media.scan_status == MediaFile.ScanStatus.INFECTED:
                raise AuthAPIError(422, "MEDIA_INFECTED", MSG_MEDIA_INFECTED)
            if msg_type == Message.Type.TEXT:
                msg_type = _TYPE_FROM_MEDIA.get(media.media_type, Message.Type.DOCUMENT)

        if msg_type not in _ALLOWED_SEND_TYPES:
            raise AuthAPIError(400, "VALIDATION_ERROR", MSG_VALIDATION, extra={"field": "type"})

        raw_content = data.get("encrypted_content") or ""
        if raw_content:
            content_bytes = _decode_b64(raw_content, "encrypted_content")
            if group_key is not None:
                content_bytes = wrapping.wrap_with_key(group_key, content_bytes)
        elif media is None:
            raise AuthAPIError(
                400, "VALIDATION_ERROR", MSG_VALIDATION, extra={"field": "encrypted_content"}
            )

    mention_ids = [str(m) for m in (data.get("mentions") or [])]
    metadata = {"client_message_id": client_message_id} if client_message_id else {}

    poll = None
    with transaction.atomic():
        message = Message.objects.create(
            type=msg_type,
            encrypted_content=content_bytes,
            conversation=conversation,
            sender=user,
            parent_message_id=data.get("parent_message_id"),
            media=media,
            priority=int(data.get("priority") or 0),
            tags=data.get("tags") or [],
            mentions=mention_ids,
            metadata=metadata,
            sent_at=timezone.now(),
        )
        if is_poll:
            poll = poll_service.create_poll(message=message, user=user, device=device, data=data)
        others.update(unread_count=F("unread_count") + 1)
        conversation.last_message = message
        conversation.last_message_at = message.sent_at
        conversation.save(update_fields=["last_message", "last_message_at", "updated_at"])

        mentioned_members = []
        if mention_ids:
            candidates = list(others.filter(user_id__in=mention_ids).select_related("user"))
            for m in candidates:
                privacy, _ = PrivacySetting.objects.get_or_create(user=m.user)
                if privacy.allow_mentions:
                    MessageMention.objects.get_or_create(message=message, mentioned_user=m.user)
                    mentioned_members.append(m)

    for other in others:
        emit(
            user=other.user,
            type_=Notification.Type.MESSAGE_NEW,
            title="Nouveau message",
            body="Vous avez reçu un nouveau message.",
            payload={"conversation_id": str(conversation.id), "message_id": str(message.id)},
            collapse_key=f"message:{conversation.id}",
        )
    for m in mentioned_members:
        emit(
            user=m.user,
            type_=Notification.Type.MESSAGE_MENTION,
            title="Vous avez été mentionné",
            body="Quelqu'un vous a mentionné dans un message.",
            payload={"conversation_id": str(conversation.id), "message_id": str(message.id)},
            collapse_key=f"mention:{message.id}",
            ignore_dnd=True,
        )
    serialized = _serialize_message(message, group_key)
    if poll is not None:
        serialized["poll"] = poll_service.serialize_poll(poll)
    realtime_service.broadcast_message_created(conversation.id, serialized)
    return serialized


# --- MSG-27 : détail --------------------------------------------------------------


def get_message_detail(*, user, pk) -> dict:
    message, _member = _get_message_and_member(user, pk)
    return _serialize_message(message, _resolve_group_key(message.conversation))


# --- MSG-24 : éditer ---------------------------------------------------------------


def edit_message(*, user, pk, encrypted_content_b64: str) -> dict:
    message, _member = _get_message_and_member(user, pk)
    if message.sender_id != user.id:
        raise AuthAPIError(403, "FORBIDDEN", MSG_FORBIDDEN)
    if timezone.now() - message.sent_at > _EDIT_WINDOW:
        raise AuthAPIError(403, "EDIT_WINDOW_EXPIRED", MSG_EDIT_EXPIRED)
    group_key = _resolve_group_key(message.conversation)
    new_content = _decode_b64(encrypted_content_b64, "encrypted_content")
    if group_key is not None:
        wrapped = wrapping.wrap_with_key(group_key, new_content)
    else:
        wrapped = new_content
    with transaction.atomic():
        MessageEdit.objects.create(
            message=message,
            previous_encrypted_content=bytes(message.encrypted_content or b""),
            edited_by=user,
            edited_at=timezone.now(),
        )
        message.encrypted_content = wrapped
        message.edited = True
        message.save(update_fields=["encrypted_content", "edited"])
    serialized = _serialize_message(message, group_key)
    realtime_service.broadcast_message_updated(message.conversation_id, serialized)
    return serialized


# --- MSG-25/26 : supprimer ----------------------------------------------------------


def delete_message(*, user, pk, scope: str) -> dict:
    message, member = _get_message_and_member(user, pk)
    scope = (scope or MessageDelete.DeleteScope.SELF).upper()
    if scope not in MessageDelete.DeleteScope.values:
        raise AuthAPIError(400, "VALIDATION_ERROR", MSG_VALIDATION, extra={"field": "scope"})

    if scope == MessageDelete.DeleteScope.SELF:
        MessageDelete.objects.get_or_create(
            message=message,
            deleted_by=user,
            delete_scope=MessageDelete.DeleteScope.SELF,
            defaults={"deleted_at": timezone.now()},
        )
        return {"deleted": True, "scope": scope}

    is_author = message.sender_id == user.id
    is_privileged = member.role in (ConversationMember.Role.OWNER, ConversationMember.Role.ADMIN)
    if not is_author and not is_privileged:
        raise AuthAPIError(403, "FORBIDDEN", MSG_FORBIDDEN)
    if is_author and not is_privileged and timezone.now() - message.sent_at > _DELETE_WINDOW:
        raise AuthAPIError(403, "DELETE_WINDOW_EXPIRED", MSG_DELETE_EXPIRED)

    with transaction.atomic():
        MessageDelete.objects.get_or_create(
            message=message,
            deleted_by=user,
            delete_scope=MessageDelete.DeleteScope.EVERYONE,
            defaults={"deleted_at": timezone.now()},
        )
        message.deleted = True
        message.encrypted_content = b""
        message.save(update_fields=["deleted", "encrypted_content"])
    realtime_service.broadcast_message_deleted(message.conversation_id, message.id, scope)
    return {"deleted": True, "scope": scope}


# --- MSG-28 : recherche --------------------------------------------------------------


def search_messages(*, user, conversation_id, q: str) -> dict:
    member = conversation_service.get_member_or_404(user, conversation_id=conversation_id)
    q = (q or "").strip()
    if len(q) < 2:
        raise AuthAPIError(400, "VALIDATION_ERROR", MSG_VALIDATION, extra={"field": "q"})
    group_key = _resolve_group_key(member.conversation)
    qs = (
        Message.objects.filter(conversation_id=conversation_id, deleted=False, tags__icontains=q)
        .exclude(deletes__delete_scope=MessageDelete.DeleteScope.SELF, deletes__deleted_by=user)
        .order_by("-sent_at")[:_SEARCH_LIMIT_MAX]
    )
    return {"results": [_serialize_message(m, group_key) for m in qs]}
