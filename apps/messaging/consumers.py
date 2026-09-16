"""WS /ws/v1/messaging/ — JWT query token= ou Bearer. Patron : PresenceConsumer (PRES-A)."""

from urllib.parse import parse_qs

from asgiref.sync import async_to_sync
from channels.generic.websocket import JsonWebsocketConsumer
from django.db import close_old_connections

from apps.iam.middlewares.authentication import session_from_access_token
from apps.iam.services.compliance_service import (
    MSG_ONBOARDING_REQUIRED,
    MSG_TOS_REQUIRED,
    onboarding_ok,
    tos_ok,
)
from apps.iam.services.rbac_service import MSG_FORBIDDEN, user_has_permission
from apps.iam.services.session_service import touch_last_activity
from apps.messaging.models import ConversationMember


def _token_from_scope(scope) -> str:
    qs = parse_qs((scope.get("query_string") or b"").decode())
    raw = (qs.get("token") or [None])[0]
    if raw:
        return raw.strip()
    for name, value in scope.get("headers") or []:
        if name == b"authorization":
            header = value.decode()
            if header.startswith("Bearer "):
                return header[len("Bearer ") :].strip()
    return ""


class MessagingConsumer(JsonWebsocketConsumer):
    def connect(self):
        close_old_connections()
        session = session_from_access_token(_token_from_scope(self.scope))
        if session is None:
            self.close(code=4401)
            return
        user = session.user
        if not tos_ok(user):
            self.accept()
            self.send_json({"type": "ERROR", "code": "TOS_REQUIRED", "message": MSG_TOS_REQUIRED})
            self.close(code=4403)
            return
        if not onboarding_ok(user):
            self.accept()
            self.send_json(
                {
                    "type": "ERROR",
                    "code": "ONBOARDING_REQUIRED",
                    "message": MSG_ONBOARDING_REQUIRED,
                }
            )
            self.close(code=4403)
            return
        if not user_has_permission(user, "messaging.conversation.read"):
            self.accept()
            self.send_json({"type": "ERROR", "code": "FORBIDDEN", "message": MSG_FORBIDDEN})
            self.close(code=4403)
            return
        self.user = user
        self.session = session
        self.subscribed = set()
        self.accept()
        touch_last_activity(session)

    def disconnect(self, code):
        close_old_connections()
        for conversation_id in list(getattr(self, "subscribed", set())):
            self._discard(conversation_id)

    def receive_json(self, content, **kwargs):
        close_old_connections()
        if not isinstance(content, dict):
            return
        kind = content.get("type")
        if kind == "PING":
            self.send_json({"type": "PONG"})
            return
        if kind == "subscribe":
            self._subscribe(content.get("conversation_ids"))
            return
        if kind == "unsubscribe":
            self._unsubscribe(content.get("conversation_ids"))
            return

    def _subscribe(self, raw_ids):
        for conversation_id in raw_ids or []:
            conversation_id = str(conversation_id)
            if conversation_id in self.subscribed:
                continue
            is_member = ConversationMember.objects.filter(
                conversation_id=conversation_id, user=self.user, active=True
            ).exists()
            if not is_member:
                continue  # pas de fuite d'existence, silencieux comme le 404 REST
            self.subscribed.add(conversation_id)
            async_to_sync(self.channel_layer.group_add)(
                f"conversation.{conversation_id}", self.channel_name
            )

    def _unsubscribe(self, raw_ids):
        for conversation_id in raw_ids or []:
            self._discard(str(conversation_id))

    def _discard(self, conversation_id: str):
        self.subscribed.discard(conversation_id)
        async_to_sync(self.channel_layer.group_discard)(
            f"conversation.{conversation_id}", self.channel_name
        )

    def message_created(self, event):
        close_old_connections()
        self.send_json(event)

    def message_updated(self, event):
        close_old_connections()
        self.send_json(event)

    def message_deleted(self, event):
        close_old_connections()
        self.send_json(event)

    def receipt_updated(self, event):
        close_old_connections()
        self.send_json(event)
