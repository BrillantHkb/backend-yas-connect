"""MESSAGERIE-D : accusés livré/lu, catch-up (after=), WebSocket temps réel."""

import asyncio
import base64
import uuid

import pytest
from asgiref.sync import async_to_sync
from channels.layers import channel_layers
from channels.testing import WebsocketCommunicator
from config.asgi import application
from django.core.cache import cache
from django.db import connections
from rest_framework.test import APIClient

from apps.iam.helpers.compliance import close_gates
from apps.iam.helpers.mfa import login_until_jwt
from apps.iam.models import PrivacySetting, Role, User
from apps.messaging.models import ConversationMember, MessageRead

PASSWORD = "Secret123!"
UA = "Mozilla/5.0 pytest"


@pytest.fixture(autouse=True)
def _inmemory_channels(settings):
    settings.CHANNEL_LAYERS = {
        "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"},
    }
    channel_layers.backends = {}


@pytest.fixture
def api():
    cache.clear()
    client = APIClient()
    client.defaults["HTTP_USER_AGENT"] = UA
    return client


@pytest.fixture
def user_role(db):
    return Role.objects.create(code="USER", name="Utilisateur", is_system=True, level=0)


def _make_user(user_role, email, username, first_name, last_name):
    return close_gates(
        User.objects.create_user(
            email=email, password=PASSWORD, username=username,
            role=user_role, first_name=first_name, last_name=last_name,
        )
    )


@pytest.fixture
def jean(user_role):
    return _make_user(user_role, "jean.dupont@yas.tg", "jean.dupont", "Jean", "Dupont")


@pytest.fixture
def marie(user_role):
    return _make_user(user_role, "marie.koevi@yas.tg", "marie.koevi", "Marie", "Koevi")


def _jwt(api, user, *, password=PASSWORD, device_uuid="web-1"):
    device = {"device_uuid": device_uuid, "platform": "WEB"}
    r = login_until_jwt(api, email=user.email, password=password, device=device)
    token = r.data["data"]["access_token"]
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return token


def _create_group(api, title, member_ids):
    return api.post(
        "/api/v1/conversations",
        {"type": "GROUP", "title": title, "member_ids": [str(i) for i in member_ids]},
        format="json",
    ).data["data"]["id"]


def _send(api, conv_id, text=b"hi"):
    body = {"type": "TEXT", "encrypted_content": base64.b64encode(text).decode()}
    return api.post(f"/api/v1/conversations/{conv_id}/messages", body, format="json").data["data"]


def _ws(path):
    return WebsocketCommunicator(application, path)


def _run_ws(coro):
    try:
        return async_to_sync(coro)()
    finally:
        connections.close_all()


# --- MSG-61 : livré ----------------------------------------------------------------


@pytest.mark.django_db
def test_mark_delivered(api, jean, marie):
    _jwt(api, jean)
    conv_id = _create_group(api, "Equipe", [marie.id])
    message = _send(api, conv_id)
    _jwt(api, marie)
    r = api.post(f"/api/v1/messages/{message['id']}/delivered")
    assert r.status_code == 200
    assert r.data["data"]["delivered_at"] is not None
    row = MessageRead.objects.get(message_id=message["id"], user=marie)
    assert row.delivered_at is not None


# --- MSG-62/63/64 : lu (respecte read_receipts_enabled) ----------------------------


@pytest.mark.django_db
def test_mark_read_enabled(api, jean, marie):
    _jwt(api, jean)
    conv_id = _create_group(api, "Equipe", [marie.id])
    message = _send(api, conv_id)
    _jwt(api, marie)
    r = api.post(f"/api/v1/messages/{message['id']}/read")
    assert r.status_code == 200
    assert r.data["data"]["read_at"] is not None


@pytest.mark.django_db
def test_mark_read_disabled_no_read_at(api, jean, marie):
    PrivacySetting.objects.update_or_create(user=marie, defaults={"read_receipts_enabled": False})
    _jwt(api, jean)
    conv_id = _create_group(api, "Equipe", [marie.id])
    message = _send(api, conv_id)
    _jwt(api, marie)
    r = api.post(f"/api/v1/messages/{message['id']}/read")
    assert r.status_code == 200
    assert r.data["data"]["read_at"] is None
    assert not MessageRead.objects.filter(message_id=message["id"], user=marie).exists()


# --- MSG-66 : tout lire -------------------------------------------------------------


@pytest.mark.django_db
def test_mark_conversation_read_resets_unread(api, jean, marie):
    _jwt(api, jean)
    conv_id = _create_group(api, "Equipe", [marie.id])
    m1 = _send(api, conv_id, b"un")
    _send(api, conv_id, b"deux")
    _jwt(api, marie)
    before = ConversationMember.objects.get(conversation_id=conv_id, user=marie)
    assert before.unread_count == 2
    r = api.post(
        f"/api/v1/conversations/{conv_id}/read",
        {"last_read_message_id": m1["id"]},
        format="json",
    )
    assert r.status_code == 200
    assert r.data["data"]["unread_count"] == 0
    after = ConversationMember.objects.get(conversation_id=conv_id, user=marie)
    assert after.unread_count == 0
    assert str(after.last_read_message_id) == m1["id"]


# --- MSG-70 : catch-up after= --------------------------------------------------------


@pytest.mark.django_db
def test_get_messages_after_ascending(api, jean, marie):
    _jwt(api, jean)
    conv_id = _create_group(api, "Equipe", [marie.id])
    m1 = _send(api, conv_id, b"un")
    _send(api, conv_id, b"deux")
    m3 = _send(api, conv_id, b"trois")
    r = api.get(f"/api/v1/conversations/{conv_id}/messages", {"after": m1["sent_at"]})
    assert r.status_code == 200
    ids = [row["id"] for row in r.data["data"]["results"]]
    assert m1["id"] not in ids
    assert m3["id"] in ids
    sent_ats = [row["sent_at"] for row in r.data["data"]["results"]]
    assert sent_ats == sorted(sent_ats)


# --- WebSocket -----------------------------------------------------------------------


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_ws_connect_without_jwt_4401(api, db):
    async def _run():
        communicator = _ws("/ws/v1/messaging/")
        connected, _ = await communicator.connect()
        assert connected is False

    _run_ws(_run)


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_ws_connect_self_without_cgu_4403(api, user_role):
    fresh = User.objects.create_user(
        email="fresh.wsd@yas.tg", password=PASSWORD, username="fresh.wsd",
        role=user_role, first_name="Fresh", last_name="Wsd",
    )
    token = _jwt(api, fresh)

    async def _run():
        communicator = _ws(f"/ws/v1/messaging/?token={token}")
        connected, _ = await communicator.connect()
        assert connected is True  # accept() avant l'envoi de l'erreur, comme PresenceConsumer
        error = await communicator.receive_json_from(timeout=2)
        assert error["code"] == "TOS_REQUIRED"

    _run_ws(_run)


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_ws_message_created_broadcast(api, jean, marie):
    jean_token = _jwt(api, jean)
    marie_token = _jwt(api, marie)
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {jean_token}")
    conv_id = _create_group(api, "Equipe", [marie.id])

    async def _run():
        watcher = _ws(f"/ws/v1/messaging/?token={marie_token}")
        connected, _ = await watcher.connect()
        assert connected
        await watcher.send_json_to({"type": "subscribe", "conversation_ids": [conv_id]})
        await asyncio.sleep(0.05)

        def _send_as_jean():
            api.credentials(HTTP_AUTHORIZATION=f"Bearer {jean_token}")
            return _send(api, conv_id, b"salut")

        message = await asyncio.to_thread(_send_as_jean)
        event = await watcher.receive_json_from(timeout=2)
        assert event["type"] == "message.created"
        assert event["conversation_id"] == conv_id
        assert event["message"]["id"] == message["id"]
        await watcher.disconnect()

    _run_ws(_run)


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_ws_subscribe_non_member_silent(api, jean, marie, user_role):
    outsider = _make_user(user_role, "outsider.ws@yas.tg", "outsider.ws", "Out", "Sider")
    jean_token = _jwt(api, jean)
    outsider_token = _jwt(api, outsider)
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {jean_token}")
    conv_id = _create_group(api, "Equipe", [marie.id])

    async def _run():
        watcher = _ws(f"/ws/v1/messaging/?token={outsider_token}")
        connected, _ = await watcher.connect()
        assert connected
        await watcher.send_json_to({"type": "subscribe", "conversation_ids": [conv_id]})
        await asyncio.sleep(0.05)

        def _send_as_jean():
            api.credentials(HTTP_AUTHORIZATION=f"Bearer {jean_token}")
            return _send(api, conv_id, b"secret")

        await asyncio.to_thread(_send_as_jean)
        assert await watcher.receive_nothing(timeout=0.3)
        await watcher.disconnect()

    _run_ws(_run)


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_ws_subscribe_over_max_rejected(api, jean):
    """Audit W13 : plafond _SUBSCRIBE_MAX (100), même principe que WATCH côté présence."""
    jean_token = _jwt(api, jean)

    async def _run():
        watcher = _ws(f"/ws/v1/messaging/?token={jean_token}")
        connected, _ = await watcher.connect()
        assert connected
        too_many = [str(uuid.uuid4()) for _ in range(101)]
        await watcher.send_json_to({"type": "subscribe", "conversation_ids": too_many})
        error = await watcher.receive_json_from(timeout=2)
        assert error["type"] == "ERROR"
        assert error["code"] == "VALIDATION_ERROR"
        await watcher.disconnect()

    _run_ws(_run)


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_ws_receipt_updated_broadcast(api, jean, marie):
    jean_token = _jwt(api, jean)
    marie_token = _jwt(api, marie)
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {jean_token}")
    conv_id = _create_group(api, "Equipe", [marie.id])
    message = _send(api, conv_id)

    async def _run():
        watcher = _ws(f"/ws/v1/messaging/?token={jean_token}")
        connected, _ = await watcher.connect()
        assert connected
        await watcher.send_json_to({"type": "subscribe", "conversation_ids": [conv_id]})
        await asyncio.sleep(0.05)

        def _deliver_as_marie():
            api.credentials(HTTP_AUTHORIZATION=f"Bearer {marie_token}")
            return api.post(f"/api/v1/messages/{message['id']}/delivered")

        r = await asyncio.to_thread(_deliver_as_marie)
        assert r.status_code == 200
        event = await watcher.receive_json_from(timeout=2)
        assert event["type"] == "receipt.updated"
        assert event["message_id"] == message["id"]
        assert event["user_id"] == str(marie.id)
        await watcher.disconnect()

    _run_ws(_run)


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_ws_ping_pong(api, jean):
    token = _jwt(api, jean)

    async def _run():
        communicator = _ws(f"/ws/v1/messaging/?token={token}")
        connected, _ = await communicator.connect()
        assert connected
        await communicator.send_json_to({"type": "PING"})
        event = await communicator.receive_json_from(timeout=2)
        assert event["type"] == "PONG"
        await communicator.disconnect()

    _run_ws(_run)
