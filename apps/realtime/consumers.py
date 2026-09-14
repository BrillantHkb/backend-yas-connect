"""WS /ws/v1/presence — JWT query token= ou Bearer. Portes AUTH-F dans le consumer."""

from urllib.parse import parse_qs

from asgiref.sync import async_to_sync
from channels.generic.websocket import JsonWebsocketConsumer
from django.db import close_old_connections

from apps.iam.exceptions import AuthAPIError
from apps.iam.middlewares.authentication import session_from_access_token
from apps.iam.models import User
from apps.iam.services.compliance_service import (
    MSG_ONBOARDING_REQUIRED,
    MSG_TOS_REQUIRED,
    onboarding_ok,
    tos_ok,
)
from apps.iam.services.presence_service import (
    mark_socket_close,
    mark_socket_open,
    parse_watch_ids,
    set_live,
    ws_status_event,
)
from apps.iam.services.rbac_service import MSG_FORBIDDEN, user_has_permission
from apps.iam.services.session_service import touch_last_activity


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


class PresenceConsumer(JsonWebsocketConsumer):
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
        if not user_has_permission(user, "iam.profile.read"):
            self.accept()
            self.send_json({"type": "ERROR", "code": "FORBIDDEN", "message": MSG_FORBIDDEN})
            self.close(code=4403)
            return
        self.user = user
        self.session = session
        self.watched = set()
        self.accept()
        device_id = session.device_id
        mark_socket_open(user, device_id=device_id)
        touch_last_activity(session)

    def disconnect(self, code):
        close_old_connections()
        user = getattr(self, "user", None)
        if user is None:
            return
        for target_id in list(getattr(self, "watched", set())):
            self._discard(target_id)
        mark_socket_close(user)

    def receive_json(self, content, **kwargs):
        close_old_connections()
        if not isinstance(content, dict):
            return
        kind = content.get("type")
        if kind == "PING":
            self._ping()
            return
        if kind == "WATCH":
            self._watch(content.get("user_ids"))
            return
        if kind == "UNWATCH":
            self._unwatch(content.get("user_ids"))
            return

    def _ping(self):
        user = User.objects.get(pk=self.user.pk)
        self.user = user
        now = set_live(user, device_id=self.session.device_id, notify=True)
        touch_last_activity(self.session)
        self.send_json({"type": "PONG", "at": now.isoformat()})

    def _watch(self, raw):
        try:
            ids = parse_watch_ids(raw)
        except AuthAPIError as exc:
            self.send_json({"type": "ERROR", "code": exc.code, "message": exc.message})
            return
        for target_id in ids:
            if target_id in self.watched:
                continue
            self.watched.add(target_id)
            async_to_sync(self.channel_layer.group_add)(
                f"presence.watch.{target_id}", self.channel_name
            )

    def _unwatch(self, raw):
        try:
            ids = parse_watch_ids(raw)
        except AuthAPIError as exc:
            self.send_json({"type": "ERROR", "code": exc.code, "message": exc.message})
            return
        for target_id in ids:
            self._discard(target_id)

    def _discard(self, target_id: str):
        self.watched.discard(target_id)
        async_to_sync(self.channel_layer.group_discard)(
            f"presence.watch.{target_id}", self.channel_name
        )

    def presence_notify(self, event):
        close_old_connections()
        try:
            target = User.objects.select_related("privacy").get(pk=event["user_id"])
        except User.DoesNotExist:
            return
        viewer = User.objects.select_related("privacy").get(pk=self.user.pk)
        self.send_json(ws_status_event(target=target, viewer=viewer))
