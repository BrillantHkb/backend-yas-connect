"""MESSAGERIE-D : diffusion WS depuis les services REST (aucune logique métier dans le consumer)."""

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer


def _group_send(conversation_id, payload: dict) -> None:
    layer = get_channel_layer()
    if layer is None:
        return
    try:
        async_to_sync(layer.group_send)(f"conversation.{conversation_id}", payload)
    except Exception:
        return


def broadcast_message_created(conversation_id, message: dict) -> None:
    _group_send(
        conversation_id,
        {"type": "message.created", "conversation_id": str(conversation_id), "message": message},
    )


def broadcast_message_updated(conversation_id, message: dict) -> None:
    _group_send(
        conversation_id,
        {"type": "message.updated", "conversation_id": str(conversation_id), "message": message},
    )


def broadcast_message_deleted(conversation_id, message_id, scope: str) -> None:
    _group_send(
        conversation_id,
        {
            "type": "message.deleted",
            "conversation_id": str(conversation_id),
            "message_id": str(message_id),
            "scope": scope,
        },
    )


def broadcast_receipt_updated(
    conversation_id, *, message_id, user_id, delivered_at=None, read_at=None
) -> None:
    _group_send(
        conversation_id,
        {
            "type": "receipt.updated",
            "message_id": str(message_id),
            "user_id": str(user_id),
            "delivered_at": delivered_at,
            "read_at": read_at,
        },
    )
