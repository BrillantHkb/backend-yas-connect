"""MESSAGERIE-D : accusés livré/lu par appareil, tout-lire par conversation."""

from django.db import transaction
from django.utils import timezone

from apps.iam.exceptions import AuthAPIError
from apps.iam.models import PrivacySetting
from apps.messaging.models import Message, MessageRead
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


# --- MSG-61 : livré ----------------------------------------------------------------


def mark_delivered(*, user, device, pk) -> dict:
    message, _member = _get_message_and_member(user, pk)
    row, _ = MessageRead.objects.update_or_create(
        message=message, user=user, device=device, defaults={"delivered_at": timezone.now()}
    )
    realtime_service.broadcast_receipt_updated(
        message.conversation_id,
        message_id=message.id,
        user_id=user.id,
        delivered_at=row.delivered_at.isoformat() if row.delivered_at else None,
        read_at=row.read_at.isoformat() if row.read_at else None,
    )
    return {"delivered_at": row.delivered_at.isoformat() if row.delivered_at else None}


# --- MSG-62/63/64 : lu (respecte read_receipts_enabled) ----------------------------


def mark_read(*, user, device, pk) -> dict:
    message, _member = _get_message_and_member(user, pk)
    privacy, _ = PrivacySetting.objects.get_or_create(user=user)
    if not privacy.read_receipts_enabled:
        return {"read_at": None}
    row, _ = MessageRead.objects.update_or_create(
        message=message, user=user, device=device, defaults={"read_at": timezone.now()}
    )
    realtime_service.broadcast_receipt_updated(
        message.conversation_id,
        message_id=message.id,
        user_id=user.id,
        delivered_at=row.delivered_at.isoformat() if row.delivered_at else None,
        read_at=row.read_at.isoformat() if row.read_at else None,
    )
    return {"read_at": row.read_at.isoformat() if row.read_at else None}


# --- MSG-66 : tout lire jusqu'à un message ------------------------------------------


def mark_conversation_read(*, user, device, conversation_id, last_read_message_id) -> dict:
    member = conversation_service.get_member_or_404(user, conversation_id=conversation_id)
    try:
        last_message = Message.objects.get(
            pk=last_read_message_id, conversation_id=conversation_id
        )
    except (Message.DoesNotExist, ValueError, TypeError) as exc:
        raise AuthAPIError(
            400, "VALIDATION_ERROR", MSG_VALIDATION, extra={"field": "last_read_message_id"}
        ) from exc

    privacy, _ = PrivacySetting.objects.get_or_create(user=user)
    if privacy.read_receipts_enabled:
        now = timezone.now()
        targets = Message.objects.filter(
            conversation_id=conversation_id, sent_at__lte=last_message.sent_at
        )
        with transaction.atomic():
            for msg in targets:
                MessageRead.objects.update_or_create(
                    message=msg, user=user, device=device, defaults={"read_at": now}
                )

    member.unread_count = 0
    member.last_read_message = last_message
    member.save(update_fields=["unread_count", "last_read_message"])
    return {"unread_count": 0}
