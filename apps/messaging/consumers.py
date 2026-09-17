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
from apps.messaging.services import realtime_service, typing_service

# Même plafond que WATCH côté présence (parse_watch_ids, WATCH_MAX) — un client
# ne doit pas pouvoir s'abonner à un nombre illimité de fils en un seul appel.
_SUBSCRIBE_MAX = 100
MSG_SUBSCRIBE_TOO_MANY = "Trop de fils dans un seul subscribe (max 100)."


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
        if kind == "typing.start":
            self._typing_start(content)
            return
        if kind == "typing.stop":
            self._typing_stop(content.get("conversation_id"))
            return

    def _subscribe(self, raw_ids):
        raw_ids = raw_ids or []
        if not isinstance(raw_ids, list) or len(raw_ids) > _SUBSCRIBE_MAX:
            self.send_json(
                {"type": "ERROR", "code": "VALIDATION_ERROR", "message": MSG_SUBSCRIBE_TOO_MANY}
            )
            return
        for conversation_id in raw_ids:
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

    def _typing_start(self, content):
        conversation_id = content.get("conversation_id")
        if not conversation_id:
            return
        conversation_id = str(conversation_id)
        is_member = ConversationMember.objects.filter(
            conversation_id=conversation_id, user=self.user, active=True
        ).exists()
        if not is_member or not typing_service.should_emit(self.user):
            return
        if not typing_service.mark_typing_start(conversation_id, self.user.id):
            return  # dédup TTL 5s (§0 jour 27)
        realtime_service.broadcast_typing_updated(
            conversation_id,
            user_id=self.user.id,
            display_name=self.user.get_full_name(),
            activity=content.get("activity") or "TEXT",
            reply_to_message_id=content.get("reply_to_message_id"),
        )

    def _typing_stop(self, conversation_id):
        if not conversation_id:
            return
        conversation_id = str(conversation_id)
        is_member = ConversationMember.objects.filter(
            conversation_id=conversation_id, user=self.user, active=True
        ).exists()
        if not is_member or not typing_service.should_emit(self.user):
            return
        typing_service.clear_typing(conversation_id, self.user.id)
        # expires_in=0 signale l'arrêt immédiat ; `activity` reste dans l'enum
        # TEXT/VOICE/CAMERA du contrat (pas de 4e valeur "STOP" inventée).
        realtime_service.broadcast_typing_updated(
            conversation_id,
            user_id=self.user.id,
            display_name=self.user.get_full_name(),
            activity="TEXT",
            expires_in=0,
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

    def reaction_updated(self, event):
        close_old_connections()
        self.send_json(event)

    def typing_updated(self, event):
        close_old_connections()
        if event.get("user_id") == str(self.user.id):
            return  # jamais d'écho à l'émetteur (§ contrat WS jour 27)
        self.send_json(event)
