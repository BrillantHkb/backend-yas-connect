"""NOTIF-R + NOTIF-A : centre de notifications, préférences, emit(), push-test, AUTH-E 28b."""

import datetime
from unittest.mock import patch

import pytest
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APIClient

from apps.iam.helpers.compliance import close_gates
from apps.iam.helpers.mfa import login_until_jwt
from apps.iam.models import Device, Role, User
from apps.notifications.models import Notification, NotificationPreference
from apps.notifications.services.notification_service import emit, ensure_preferences

PASSWORD = "Secret123!"
DEVICE = {"device_uuid": "test-web-1", "platform": "WEB"}
UA = "Mozilla/5.0 pytest"


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
            email="jean.dupont@yas.tg", password=PASSWORD, username="jean.dupont",
            role=user_role, first_name="Jean", last_name="Dupont",
        )
    )


@pytest.fixture
def marie(user_role):
    return close_gates(
        User.objects.create_user(
            email="marie.koevi@yas.tg", password=PASSWORD, username="marie.koevi",
            role=user_role, first_name="Marie", last_name="Koevi",
        )
    )


def _jwt(api, user, *, password=PASSWORD, device=DEVICE):
    r = login_until_jwt(api, email=user.email, password=password, device=device)
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {r.data['data']['access_token']}")
    return r


# --- emit() : moteur ------------------------------------------------------------


@pytest.mark.django_db
def test_emit_idempotent_within_window(jean):
    row1 = emit(user=jean, type_="SYSTEM", title="a", collapse_key="test:1")
    row2 = emit(user=jean, type_="SYSTEM", title="b", collapse_key="test:1")
    assert row1.id == row2.id
    assert Notification.objects.filter(user=jean, collapse_key="test:1").count() == 1
    row2.refresh_from_db()
    assert row2.title == "b"


@pytest.mark.django_db
def test_emit_push_disabled_inserts_inapp_no_push(jean):
    prefs = ensure_preferences(jean)
    prefs.push_enabled = False
    prefs.save(update_fields=["push_enabled"])
    row = emit(user=jean, type_="SYSTEM", title="hello")
    assert row is not None
    assert row.pushed_at is None


@pytest.mark.django_db
def test_emit_dnd_blocks_push(jean):
    prefs = ensure_preferences(jean)
    prefs.quiet_hours_enabled = True
    prefs.quiet_hours_start = datetime.time(0, 0, 0)
    prefs.quiet_hours_end = datetime.time(23, 59, 59)
    prefs.save(update_fields=["quiet_hours_enabled", "quiet_hours_start", "quiet_hours_end"])
    Device.objects.create(
        user=jean, device_uuid="d1", platform=Device.Platform.ANDROID, push_token="tok",
    )
    with patch(
        "apps.notifications.services.notification_service.push_worker.send_push"
    ) as mocked:
        row = emit(user=jean, type_="MESSAGE_NEW", title="x", collapse_key="msg:1")
        mocked.assert_not_called()
    assert row.pushed_at is None


@pytest.mark.django_db
def test_emit_ignore_dnd_for_call_incoming(jean):
    prefs = ensure_preferences(jean)
    prefs.quiet_hours_enabled = True
    prefs.quiet_hours_start = datetime.time(0, 0, 0)
    prefs.quiet_hours_end = datetime.time(23, 59, 59)
    prefs.save(update_fields=["quiet_hours_enabled", "quiet_hours_start", "quiet_hours_end"])
    Device.objects.create(
        user=jean, device_uuid="d1", platform=Device.Platform.ANDROID, push_token="tok",
    )
    with patch(
        "apps.notifications.services.notification_service.push_worker.send_push",
        return_value={"channel": "fcm", "status": "sent"},
    ):
        row = emit(
            user=jean, type_=Notification.Type.CALL_INCOMING, title="Appel",
            collapse_key="call:1", ignore_dnd=True,
        )
    row.refresh_from_db()
    assert row.pushed_at is not None


@pytest.mark.django_db
def test_emit_call_cancelled_no_inbox_row(jean):
    row = emit(user=jean, type_="CALL_CANCELLED", title="x", collapse_key="call:2")
    assert row is None
    assert not Notification.objects.filter(user=jean, collapse_key="call:2").exists()


# --- Inbox / prefs HTTP ----------------------------------------------------------


@pytest.mark.django_db
def test_inbox_isolation_404(api, jean, marie):
    other = Notification.objects.create(user=marie, type="SYSTEM", title="secret")
    _jwt(api, jean)
    r = api.post(f"/api/v1/notifications/{other.id}/read")
    assert r.status_code == 404


@pytest.mark.django_db
def test_mark_read_idempotent(api, jean):
    row = Notification.objects.create(user=jean, type="SYSTEM", title="x")
    _jwt(api, jean)
    r1 = api.post(f"/api/v1/notifications/{row.id}/read")
    r2 = api.post(f"/api/v1/notifications/{row.id}/read")
    assert r1.status_code == 204
    assert r2.status_code == 204


@pytest.mark.django_db
def test_read_all(api, jean):
    Notification.objects.create(user=jean, type="SYSTEM", title="a")
    Notification.objects.create(user=jean, type="SYSTEM", title="b")
    _jwt(api, jean)
    r = api.post("/api/v1/notifications/read-all")
    assert r.status_code == 204
    assert not Notification.objects.filter(user=jean, read_at__isnull=True).exists()


@pytest.mark.django_db
def test_unread_count(api, jean):
    _jwt(api, jean)
    before = api.get("/api/v1/notifications/unread-count").data["data"]["count"]
    Notification.objects.create(user=jean, type="SYSTEM", title="a")
    Notification.objects.create(user=jean, type="SYSTEM", title="b", read_at=timezone.now())
    after = api.get("/api/v1/notifications/unread-count").data["data"]["count"]
    assert after == before + 1


@pytest.mark.django_db
def test_preferences_provisioned_at_register():
    body = {
        "email": "neuf.notif@yas.tg", "password": "SecretApp456!",
        "first_name": "Neuf", "last_name": "Notif", "phone": "+22890111199",
        "job_title": "RH", "region_id": None, "segment_id": None,
    }
    from apps.annuaire.models import Segment, SegmentType
    from apps.iam.models import Region

    Role.objects.get_or_create(code="USER", defaults={"name": "Utilisateur", "is_system": True})
    region = Region.objects.create(code="MARITIME2", name="Maritime 2")
    seg_type = SegmentType.objects.create(code="DIRECTION2", name="Direction 2", level=0)
    segment = Segment.objects.create(
        code="YAS2", name="YAS 2", segment_type=seg_type, is_active=True
    )
    body["region_id"] = str(region.id)
    body["segment_id"] = str(segment.id)

    api = APIClient()
    api.defaults["HTTP_USER_AGENT"] = UA
    r = api.post("/api/v1/auth/register", body, format="json")
    assert r.status_code == 201
    user = User.objects.get(email="neuf.notif@yas.tg")
    assert NotificationPreference.objects.filter(user=user).exists()


@pytest.mark.django_db
def test_preferences_patch_whitelist(api, jean):
    _jwt(api, jean)
    r = api.patch(
        "/api/v1/notification-preferences",
        {"push_enabled": False, "quiet_hours_start": "22:00:00", "quiet_hours_end": "06:00:00"},
        format="json",
    )
    assert r.status_code == 200
    assert r.data["data"]["push_enabled"] is False
    assert r.data["data"]["quiet_hours_start"] == "22:00:00"


# --- DEVICE_NEW réel --------------------------------------------------------------


@pytest.mark.django_db
def test_device_new_real_notification_on_login(api, jean):
    _jwt(api, jean)
    r = api.get("/api/v1/notifications")
    types = {row["type"] for row in r.data["data"]["results"]}
    assert "DEVICE_NEW" in types


# --- NOTIF-17 : push-test ---------------------------------------------------------


@pytest.mark.django_db
def test_push_test_no_token_skipped(api, jean):
    _jwt(api, jean)
    r = api.post("/api/v1/me/devices/current/push-test")
    assert r.status_code == 200
    statuses = {c["status"] for c in r.data["data"]["channels"]}
    assert statuses <= {"skipped_no_token", "not_configured"}
    assert "emitted_at" in r.data["data"]


@pytest.mark.django_db
def test_push_test_rate_limited(api, jean):
    _jwt(api, jean)
    api.post("/api/v1/me/devices/current/push-test")
    r = api.post("/api/v1/me/devices/current/push-test")
    assert r.status_code == 429
    assert r.data["code"] == "RATE_LIMITED"


@pytest.mark.django_db
def test_push_test_no_inbox_row(api, jean):
    _jwt(api, jean)
    api.post("/api/v1/me/devices/current/push-test")
    assert not Notification.objects.filter(user=jean, type="PUSH_TEST").exists()


# --- AUTH-E 28b : voip_push_token --------------------------------------------------


@pytest.mark.django_db
def test_patch_voip_push_token_alone_keeps_push_token(api, jean):
    _jwt(api, jean)
    device = Device.objects.get(user=jean, device_uuid=DEVICE["device_uuid"])
    device.push_token = "existing-fcm-token"
    device.save(update_fields=["push_token"])
    r = api.patch(
        "/api/v1/me/devices/current", {"voip_push_token": "new-voip-token"}, format="json"
    )
    assert r.status_code == 200
    device.refresh_from_db()
    assert device.push_token == "existing-fcm-token"
    assert device.voip_push_token == "new-voip-token"


# --- Auth / portes -----------------------------------------------------------------


@pytest.mark.django_db
def test_without_jwt_401(api, db):
    r = api.get("/api/v1/notifications")
    assert r.status_code == 401


@pytest.mark.django_db
def test_self_without_tos_403(api, user_role):
    fresh = User.objects.create_user(
        email="fresh.notif@yas.tg", password=PASSWORD, username="fresh.notif",
        role=user_role, first_name="Fresh", last_name="Notif",
    )
    _jwt(api, fresh)
    r = api.get("/api/v1/notifications")
    assert r.status_code == 403
    assert r.data["code"] == "TOS_REQUIRED"


@pytest.mark.django_db
def test_schema_has_notif_paths(api, db):
    schema = api.get("/api/schema/")
    assert schema.status_code == 200
    text = schema.content.decode()
    assert "/api/v1/notifications" in text
    assert "/api/v1/me/devices/current/push-test" in text
