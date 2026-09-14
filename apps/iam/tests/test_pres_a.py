"""PRES-A : liveness Redis, effective_status, PATCH, WS, privacy PROF-25."""

import asyncio
from datetime import datetime, timedelta, timezone as dt_timezone

import pytest
from asgiref.sync import async_to_sync
from channels.layers import channel_layers
from channels.testing import WebsocketCommunicator
from django.core.cache import cache
from django.db import connections
from django.utils import timezone
from rest_framework.test import APIClient

from apps.annuaire.models import Segment, SegmentType
from apps.iam.helpers.compliance import close_gates
from apps.iam.helpers.mfa import login_until_jwt
from apps.iam.models import AuditLog, Role, RolePermission, Session, User, Visibility
from apps.iam.services.presence_service import (
    LIVE_KEY,
    badge_for,
    clear_live,
    effective_status,
    on_call_ended,
    on_call_started,
    set_live,
)
from apps.iam.services.rbac_service import invalidate_role_cache
from config.asgi import application

DEVICE = {"device_uuid": "test-web-1", "platform": "WEB"}
UA = "Mozilla/5.0 pytest"
PASSWORD = "Secret123!"


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


@pytest.fixture
def jean(user_role):
    return close_gates(
        User.objects.create_user(
            email="jean.dupont@yas.tg",
            password=PASSWORD,
            username="jean.dupont",
            role=user_role,
            first_name="Jean",
            last_name="Dupont",
        )
    )


@pytest.fixture
def marie(user_role):
    return close_gates(
        User.objects.create_user(
            email="marie.koevi@yas.tg",
            password=PASSWORD,
            username="marie.koevi",
            role=user_role,
            first_name="Marie",
            last_name="Koevi",
        )
    )


def _jwt(api, user, *, password=PASSWORD, device=DEVICE):
    r = login_until_jwt(api, email=user.email, password=password, device=device)
    token = r.data["data"]["access_token"]
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return token


def _ws(path):
    return WebsocketCommunicator(application, path)


def _run_ws(coro):
    try:
        return async_to_sync(coro)()
    finally:
        connections.close_all()


def _parse_iso(value):
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


@pytest.mark.django_db
def test_login_without_heartbeat_is_offline(api, jean, marie):
    _jwt(api, jean)
    me = api.get("/api/v1/me/")
    assert me.status_code == 200
    user = me.data["data"]["user"]
    assert user["connection"] == User.PresenceStatus.OFFLINE
    assert user["status"] == User.PresenceStatus.OFFLINE
    assert user["badge"] == "grey"
    assert "last_login" in user
    col = api.get(f"/api/v1/users/{marie.id}")
    assert col.status_code == 200
    other = col.data["data"]["user"]
    assert other["status"] == User.PresenceStatus.OFFLINE
    assert other["badge"] == "grey"
    assert "connection" not in other
    assert "availability" not in other
    assert "last_login" not in other


@pytest.mark.django_db
def test_heartbeat_sets_online_green(api, jean, marie):
    _jwt(api, jean)
    r = api.post("/api/v1/me/presence/heartbeat", {}, format="json")
    assert r.status_code == 200
    assert r.data["data"]["at"]
    me = api.get("/api/v1/me/")
    user = me.data["data"]["user"]
    assert user["status"] == User.PresenceStatus.ONLINE
    assert user["connection"] == User.PresenceStatus.ONLINE
    assert user["badge"] == "green"
    _jwt(api, marie)
    col = api.get(f"/api/v1/users/{jean.id}")
    assert col.data["data"]["user"]["status"] == User.PresenceStatus.ONLINE
    assert col.data["data"]["user"]["badge"] == "green"


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_last_ws_close_goes_offline(api, jean):
    token = _jwt(api, jean)

    async def _run():
        comm = _ws(f"/ws/v1/presence?token={token}")
        connected, _ = await comm.connect()
        assert connected
        await comm.disconnect()

    _run_ws(_run)
    me = api.get("/api/v1/me/")
    assert me.data["data"]["user"]["connection"] == User.PresenceStatus.OFFLINE
    assert me.data["data"]["user"]["status"] == User.PresenceStatus.OFFLINE


@pytest.mark.django_db
def test_second_heartbeat_debounces_session(api, jean):
    _jwt(api, jean)
    session = Session.objects.get(user=jean, is_active=True)
    session.last_activity = timezone.now() - timedelta(seconds=61)
    session.save(update_fields=["last_activity", "updated_at"])
    api.post("/api/v1/me/presence/heartbeat", {}, format="json")
    session.refresh_from_db()
    written = session.last_activity
    api.post("/api/v1/me/presence/heartbeat", {}, format="json")
    session.refresh_from_db()
    assert session.last_activity == written


@pytest.mark.django_db
def test_session_heartbeat_does_not_set_status(api, jean):
    _jwt(api, jean)
    before = jean.status
    session = Session.objects.get(user=jean, is_active=True)
    session.last_activity = timezone.now() - timedelta(seconds=61)
    session.save(update_fields=["last_activity", "updated_at"])
    r = api.post("/api/v1/me/sessions/current/heartbeat", {}, format="json")
    assert r.status_code == 200
    jean.refresh_from_db()
    assert jean.status == before
    me = api.get("/api/v1/me/")
    assert me.data["data"]["user"]["connection"] == User.PresenceStatus.OFFLINE


@pytest.mark.django_db
def test_stale_key_is_away_orange(api, jean):
    _jwt(api, jean)
    cache.set(
        LIVE_KEY.format(jean.id),
        {"at": (timezone.now() - timedelta(minutes=6)).timestamp(), "device_id": None},
        timeout=90,
    )
    me = api.get("/api/v1/me/")
    user = me.data["data"]["user"]
    assert user["status"] == User.PresenceStatus.AWAY
    assert user["connection"] == User.PresenceStatus.AWAY
    assert user["badge"] == "orange"


@pytest.mark.django_db
@pytest.mark.parametrize("status,code", [
    ("BUSY", "STATUS_UNKNOWN"),
    ("DND", "STATUS_UNKNOWN"),
    ("IN_FIELD", "STATUS_UNKNOWN"),
    ("AWAY", "STATUS_NOT_SETTABLE"),
    ("OFFLINE", "STATUS_NOT_SETTABLE"),
    ("IN_MEETING", "STATUS_RESERVED"),
])
def test_patch_status_rejected(api, jean, status, code):
    _jwt(api, jean)
    r = api.patch("/api/v1/me/presence", {"status": status}, format="json")
    assert r.status_code == 400
    assert r.data["code"] == code


@pytest.mark.django_db
def test_on_call_started_purple_when_live(api, jean, marie):
    _jwt(api, jean)
    set_live(jean)
    on_call_started(jean)
    jean.refresh_from_db()
    assert jean.status == User.PresenceStatus.IN_MEETING
    me = api.get("/api/v1/me/")
    assert me.data["data"]["user"]["status"] == User.PresenceStatus.IN_MEETING
    assert me.data["data"]["user"]["badge"] == "purple"
    assert me.data["data"]["user"]["availability"] == User.PresenceStatus.IN_MEETING
    _jwt(api, marie)
    col = api.get(f"/api/v1/users/{jean.id}")
    assert col.data["data"]["user"]["status"] == User.PresenceStatus.IN_MEETING
    assert col.data["data"]["user"]["badge"] == "purple"


@pytest.mark.django_db
def test_on_call_not_live_others_offline_self_availability(api, jean, marie):
    _jwt(api, jean)
    on_call_started(jean)
    jean.refresh_from_db()
    me = api.get("/api/v1/me/")
    assert me.data["data"]["user"]["status"] == User.PresenceStatus.OFFLINE
    assert me.data["data"]["user"]["availability"] == User.PresenceStatus.IN_MEETING
    _jwt(api, marie)
    col = api.get(f"/api/v1/users/{jean.id}")
    assert col.data["data"]["user"]["status"] == User.PresenceStatus.OFFLINE
    assert col.data["data"]["user"]["badge"] == "grey"


@pytest.mark.django_db
def test_on_call_ended_live_is_online(api, jean):
    _jwt(api, jean)
    set_live(jean)
    on_call_started(jean)
    on_call_ended(jean)
    me = api.get("/api/v1/me/")
    assert me.data["data"]["user"]["status"] == User.PresenceStatus.ONLINE
    assert me.data["data"]["user"]["availability"] == User.PresenceStatus.ONLINE


@pytest.mark.django_db
def test_last_seen_after_heartbeat_ge_session(api, jean):
    _jwt(api, jean)
    session = Session.objects.get(user=jean, is_active=True)
    session.last_activity = timezone.now() - timedelta(seconds=61)
    session.save(update_fields=["last_activity", "updated_at"])
    api.post("/api/v1/me/presence/heartbeat", {}, format="json")
    session.refresh_from_db()
    me = api.get("/api/v1/me/")
    seen = me.data["data"]["user"]["last_seen"]
    assert seen is not None
    seen_dt = _parse_iso(seen)
    activity = session.last_activity
    if timezone.is_naive(activity):
        activity = timezone.make_aware(activity, dt_timezone.utc)
    assert seen_dt >= activity


@pytest.mark.django_db
def test_me_has_last_login_colleague_does_not(api, jean, marie):
    _jwt(api, jean)
    me = api.get("/api/v1/me/")
    assert "last_login" in me.data["data"]["user"]
    col = api.get(f"/api/v1/users/{marie.id}")
    assert "last_login" not in col.data["data"]["user"]


@pytest.mark.django_db
def test_message_141_validation_error(api, jean):
    _jwt(api, jean)
    r = api.patch("/api/v1/me/presence", {"status_message": "x" * 141}, format="json")
    assert r.status_code == 400
    assert r.data["code"] == "VALIDATION_ERROR"


@pytest.mark.django_db
def test_status_until_field_unknown(api, jean):
    _jwt(api, jean)
    r = api.patch("/api/v1/me/presence", {"status_until": "2026-01-01T00:00:00Z"}, format="json")
    assert r.status_code == 400
    assert r.data["code"] == "FIELD_UNKNOWN"


@pytest.mark.django_db
def test_patch_message_and_clear_sticky_audits(api, jean):
    _jwt(api, jean)
    set_live(jean)
    on_call_started(jean)
    r = api.patch(
        "/api/v1/me/presence",
        {"status": "ONLINE", "status_message": "Terrain Lomé"},
        format="json",
    )
    assert r.status_code == 200
    data = r.data["data"]
    assert data["status_message"] == "Terrain Lomé"
    assert data["availability"] == User.PresenceStatus.ONLINE
    assert AuditLog.objects.filter(action="PRESENCE_SET", user=jean).exists()
    cleared = api.patch("/api/v1/me/presence", {"status_message": ""}, format="json")
    assert cleared.status_code == 200
    assert cleared.data["data"]["status_message"] == ""


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_watcher_receives_status_event(api, jean, marie):
    jean_token = _jwt(api, jean)
    marie_token = _jwt(api, marie)

    async def _run():
        watcher = _ws(f"/ws/v1/presence?token={jean_token}")
        connected, _ = await watcher.connect()
        assert connected
        await watcher.send_json_to({"type": "WATCH", "user_ids": [str(marie.id)]})
        await asyncio.sleep(0.05)

        def _heartbeat():
            api.credentials(HTTP_AUTHORIZATION=f"Bearer {marie_token}")
            return api.post("/api/v1/me/presence/heartbeat", {}, format="json")

        r = await asyncio.to_thread(_heartbeat)
        assert r.status_code == 200
        event = await watcher.receive_json_from(timeout=2)
        assert event["type"] == "USER_STATUS_CHANGED"
        assert event["user_id"] == str(marie.id)
        assert event["status"] == User.PresenceStatus.ONLINE
        assert event["badge"] == "green"
        await watcher.disconnect()

    _run_ws(_run)


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_nobody_hides_status_get_and_ws(api, jean, marie):
    priv = marie.privacy
    priv.online_status_visibility = Visibility.NOBODY
    priv.save(update_fields=["online_status_visibility", "updated_at"])
    set_live(marie)
    jean_token = _jwt(api, jean)
    col = api.get(f"/api/v1/users/{marie.id}")
    user = col.data["data"]["user"]
    assert user["status"] is None
    assert user["badge"] is None
    assert user["status_message"] is None

    async def _run():
        watcher = _ws(f"/ws/v1/presence?token={jean_token}")
        connected, _ = await watcher.connect()
        assert connected
        await watcher.send_json_to({"type": "WATCH", "user_ids": [str(marie.id)]})
        await asyncio.sleep(0.05)
        await asyncio.to_thread(lambda: set_live(marie, notify=True))
        event = await watcher.receive_json_from(timeout=2)
        assert event["status"] is None
        assert event["badge"] is None
        assert "status_message" not in event
        await watcher.disconnect()

    _run_ws(_run)


@pytest.mark.django_db
def test_contacts_other_segment_hides_status(api, jean, marie):
    st = SegmentType.objects.create(code="SERVICE", name="Service", level=2)
    a = Segment.objects.create(code="NOC", name="NOC", segment_type=st, is_active=True)
    b = Segment.objects.create(code="RH", name="RH", segment_type=st, is_active=True)
    jean.segment_id = a.id
    jean.save(update_fields=["segment_id", "updated_at"])
    marie.segment_id = b.id
    marie.save(update_fields=["segment_id", "updated_at"])
    priv = marie.privacy
    priv.online_status_visibility = Visibility.CONTACTS
    priv.save(update_fields=["online_status_visibility", "updated_at"])
    set_live(marie)
    _jwt(api, jean)
    col = api.get(f"/api/v1/users/{marie.id}")
    assert col.data["data"]["user"]["status"] is None
    assert col.data["data"]["user"]["badge"] is None


@pytest.mark.django_db
def test_badge_mapping():
    assert badge_for(User.PresenceStatus.ONLINE) == "green"
    assert badge_for(User.PresenceStatus.AWAY) == "orange"
    assert badge_for(User.PresenceStatus.IN_MEETING) == "purple"
    assert badge_for(User.PresenceStatus.OFFLINE) == "grey"
    assert badge_for(None) is None


@pytest.mark.django_db
def test_presence_before_wizard_403(api, user_role):
    from django.conf import settings

    fresh = User.objects.create_user(
        email="neuf@yas.tg",
        password=PASSWORD,
        username="user.neuf",
        role=user_role,
        first_name="Neuf",
        last_name="Compte",
    )
    _jwt(api, fresh)
    blocked = api.post("/api/v1/me/presence/heartbeat", {}, format="json")
    assert blocked.status_code == 403
    assert blocked.data["code"] == "TOS_REQUIRED"
    api.post("/api/v1/me/tos/accept", {"version": settings.YAS_TOS_VERSION}, format="json")
    r = api.post("/api/v1/me/presence/heartbeat", {}, format="json")
    assert r.status_code == 403
    assert r.data["code"] == "ONBOARDING_REQUIRED"


@pytest.mark.django_db
def test_ws_without_jwt_4401():
    async def _run():
        comm = _ws("/ws/v1/presence")
        connected, _ = await comm.connect()
        assert connected is False

    _run_ws(_run)


@pytest.mark.django_db
def test_without_presence_update_403(api, jean):
    RolePermission.objects.filter(
        role=jean.role, permission__code="iam.presence.update"
    ).delete()
    invalidate_role_cache(jean.role_id)
    _jwt(api, jean)
    r = api.patch("/api/v1/me/presence", {"status_message": "x"}, format="json")
    assert r.status_code == 403
    assert r.data["code"] == "FORBIDDEN"


@pytest.mark.django_db
def test_presence_without_jwt_401(api):
    r = api.patch("/api/v1/me/presence", {"status_message": "x"}, format="json")
    assert r.status_code == 401


@pytest.mark.django_db
def test_schema_has_me_presence(api, db):
    schema = api.get("/api/schema/")
    assert schema.status_code == 200
    text = schema.content.decode()
    assert "/api/v1/me/presence" in text
    assert "/ws/v1/presence" in text


@pytest.mark.django_db
def test_effective_offline_without_key(jean):
    jean.status = User.PresenceStatus.IN_MEETING
    jean.save(update_fields=["status", "updated_at"])
    assert effective_status(jean) == User.PresenceStatus.OFFLINE
    clear_live(jean)
