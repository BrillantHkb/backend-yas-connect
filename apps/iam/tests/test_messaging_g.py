"""MESSAGERIE-G : indicateurs de saisie (typing.start/stop/updated, WS)."""

import asyncio

import pytest
from asgiref.sync import async_to_sync
from channels.layers import channel_layers
from channels.testing import WebsocketCommunicator
from django.core.cache import cache
from django.db import connections
from rest_framework.test import APIClient

from apps.iam.helpers.compliance import close_gates
from apps.iam.helpers.mfa import login_until_jwt
from apps.iam.models import PrivacySetting, Role, User, UserPreference
from config.asgi import application

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


def _ws(path):
    return WebsocketCommunicator(application, path)


def _run_ws(coro):
    try:
        return async_to_sync(coro)()
    finally:
        connections.close_all()


async def _subscribe(communicator, conv_id):
    await communicator.send_json_to({"type": "subscribe", "conversation_ids": [conv_id]})
    await asyncio.sleep(0.05)


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_typing_start_reaches_other_member(api, jean, marie):
    jean_token = _jwt(api, jean)
    marie_token = _jwt(api, marie)
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {jean_token}")
    conv_id = _create_group(api, "Equipe", [marie.id])

    async def _run():
        emitter = _ws(f"/ws/v1/messaging/?token={jean_token}")
        watcher = _ws(f"/ws/v1/messaging/?token={marie_token}")
        assert (await emitter.connect())[0]
        assert (await watcher.connect())[0]
        await _subscribe(emitter, conv_id)
        await _subscribe(watcher, conv_id)

        payload = {"type": "typing.start", "conversation_id": conv_id, "activity": "TEXT"}
        await emitter.send_json_to(payload)
        event = await watcher.receive_json_from(timeout=2)
        assert event["type"] == "typing.updated"
        assert event["user_id"] == str(jean.id)
        assert event["activity"] == "TEXT"
        assert event["expires_in"] == 5
        await emitter.disconnect()
        await watcher.disconnect()

    _run_ws(_run)


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_typing_start_no_echo_to_emitter(api, jean, marie):
    jean_token = _jwt(api, jean)
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {jean_token}")
    conv_id = _create_group(api, "Equipe", [marie.id])

    async def _run():
        emitter = _ws(f"/ws/v1/messaging/?token={jean_token}")
        assert (await emitter.connect())[0]
        await _subscribe(emitter, conv_id)
        payload = {"type": "typing.start", "conversation_id": conv_id, "activity": "TEXT"}
        await emitter.send_json_to(payload)
        assert await emitter.receive_nothing(timeout=0.3)
        await emitter.disconnect()

    _run_ws(_run)


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_typing_start_dedup_within_ttl(api, jean, marie):
    jean_token = _jwt(api, jean)
    marie_token = _jwt(api, marie)
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {jean_token}")
    conv_id = _create_group(api, "Equipe", [marie.id])

    async def _run():
        emitter = _ws(f"/ws/v1/messaging/?token={jean_token}")
        watcher = _ws(f"/ws/v1/messaging/?token={marie_token}")
        assert (await emitter.connect())[0]
        assert (await watcher.connect())[0]
        await _subscribe(emitter, conv_id)
        await _subscribe(watcher, conv_id)

        payload = {"type": "typing.start", "conversation_id": conv_id, "activity": "TEXT"}
        await emitter.send_json_to(payload)
        await watcher.receive_json_from(timeout=2)
        await emitter.send_json_to(payload)  # rejoué < 5s -> dédupliqué
        assert await watcher.receive_nothing(timeout=0.3)
        await emitter.disconnect()
        await watcher.disconnect()

    _run_ws(_run)


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_typing_start_respects_prefs_disabled(api, jean, marie):
    UserPreference.objects.update_or_create(user=jean, defaults={"typing_indicator": False})
    jean_token = _jwt(api, jean)
    marie_token = _jwt(api, marie)
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {jean_token}")
    conv_id = _create_group(api, "Equipe", [marie.id])

    async def _run():
        emitter = _ws(f"/ws/v1/messaging/?token={jean_token}")
        watcher = _ws(f"/ws/v1/messaging/?token={marie_token}")
        assert (await emitter.connect())[0]
        assert (await watcher.connect())[0]
        await _subscribe(emitter, conv_id)
        await _subscribe(watcher, conv_id)

        payload = {"type": "typing.start", "conversation_id": conv_id, "activity": "TEXT"}
        await emitter.send_json_to(payload)
        assert await watcher.receive_nothing(timeout=0.3)
        await emitter.disconnect()
        await watcher.disconnect()

    _run_ws(_run)


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_typing_start_respects_privacy_disabled(api, jean, marie):
    PrivacySetting.objects.update_or_create(user=jean, defaults={"typing_indicator_enabled": False})
    jean_token = _jwt(api, jean)
    marie_token = _jwt(api, marie)
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {jean_token}")
    conv_id = _create_group(api, "Equipe", [marie.id])

    async def _run():
        emitter = _ws(f"/ws/v1/messaging/?token={jean_token}")
        watcher = _ws(f"/ws/v1/messaging/?token={marie_token}")
        assert (await emitter.connect())[0]
        assert (await watcher.connect())[0]
        await _subscribe(emitter, conv_id)
        await _subscribe(watcher, conv_id)

        payload = {"type": "typing.start", "conversation_id": conv_id, "activity": "TEXT"}
        await emitter.send_json_to(payload)
        assert await watcher.receive_nothing(timeout=0.3)
        await emitter.disconnect()
        await watcher.disconnect()

    _run_ws(_run)


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_typing_stop_never_deduplicated(api, jean, marie):
    jean_token = _jwt(api, jean)
    marie_token = _jwt(api, marie)
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {jean_token}")
    conv_id = _create_group(api, "Equipe", [marie.id])

    async def _run():
        emitter = _ws(f"/ws/v1/messaging/?token={jean_token}")
        watcher = _ws(f"/ws/v1/messaging/?token={marie_token}")
        assert (await emitter.connect())[0]
        assert (await watcher.connect())[0]
        await _subscribe(emitter, conv_id)
        await _subscribe(watcher, conv_id)

        await emitter.send_json_to(
            {"type": "typing.start", "conversation_id": conv_id, "activity": "TEXT"}
        )
        await watcher.receive_json_from(timeout=2)
        await emitter.send_json_to({"type": "typing.stop", "conversation_id": conv_id})
        event = await watcher.receive_json_from(timeout=2)
        assert event["type"] == "typing.updated"
        assert event["expires_in"] == 0
        await emitter.disconnect()
        await watcher.disconnect()

    _run_ws(_run)
