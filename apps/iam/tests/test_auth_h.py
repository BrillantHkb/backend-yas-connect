"""AUTH-H : logout, liste sessions, idle / plafond, heartbeat, blacklist JTI."""

from datetime import timedelta
from uuid import uuid4

import pytest
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APIClient

from apps.iam.helpers.compliance import close_gates
from apps.iam.helpers.mfa import login_until_jwt, totp_now
from apps.iam.jobs import reap_sessions
from apps.iam.models import Device, RefreshToken, Role, Session, User
from apps.iam.services.jti_blacklist import jti_blocked
from apps.iam.services.token_service import hash_refresh_token

DEVICE = {"device_uuid": "test-web-1", "platform": "WEB", "device_name": "PC lab"}
DEVICE2 = {"device_uuid": "test-web-2", "platform": "WEB", "device_name": "Tel lab"}
UA = "Mozilla/5.0 pytest"
PASSWORD = "Secret123!"
NEW_PASSWORD = "SecretApp456!"


@pytest.fixture
def api():
    cache.clear()
    client = APIClient()
    client.defaults["HTTP_USER_AGENT"] = UA
    return client


@pytest.fixture
def role(db):
    return Role.objects.create(code="USER", name="Utilisateur", is_system=True, level=0)


@pytest.fixture
def user_ok(role):
    return close_gates(
        User.objects.create_user(
            email="jean.dupont@yas.tg",
            password=PASSWORD,
            username="jean.dupont",
            role=role,
            first_name="Jean",
            last_name="Dupont",
        )
    )


@pytest.fixture
def other_user(role):
    return close_gates(
        User.objects.create_user(
            email="marie@yas.tg",
            password=PASSWORD,
            username="marie.koevi",
            role=role,
        )
    )


@pytest.fixture
def user_fresh(role):
    return User.objects.create_user(
        email="neuf@yas.tg",
        password=PASSWORD,
        username="user.neuf",
        role=role,
    )


def _body(r):
    data = getattr(r, "data", None)
    if isinstance(data, dict):
        return data
    return r.json()


def _jwt(api, user, device=DEVICE, password=PASSWORD):
    r = login_until_jwt(api, email=user.email, password=password, device=device)
    token = r.data["data"]["access_token"]
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return r


@pytest.mark.django_db
def test_complete_login_session_expires_30_days(api, user_ok):
    _jwt(api, user_ok)
    session = Session.objects.get(user=user_ok, is_active=True)
    remaining = (session.expires_at - timezone.now()).total_seconds()
    assert remaining > 29 * 24 * 3600
    assert remaining <= settings.YAS_SESSION_ABSOLUTE_SECONDS + 5
    assert remaining > settings.YAS_JWT_ACCESS_TTL_SECONDS * 10


@pytest.mark.django_db
def test_refresh_ok_keeps_session_expires_at(api, user_ok):
    first = login_until_jwt(api, email=user_ok.email, password=PASSWORD, device=DEVICE)
    old = first.data["data"]["refresh_token"]
    session = Session.objects.get(user=user_ok, is_active=True)
    before = session.expires_at
    r = api.post("/api/v1/auth/refresh", {"refresh_token": old}, format="json")
    assert r.status_code == 200
    assert r.data["data"]["refresh_token"] != old
    assert "access_token" in r.data["data"]
    row = RefreshToken.objects.get(token_hash=hash_refresh_token(old))
    assert row.revoked_reason == "ROTATED"
    session.refresh_from_db()
    assert session.expires_at == before


@pytest.mark.django_db
def test_refresh_reuse_force_logout(api, user_ok):
    first = login_until_jwt(api, email=user_ok.email, password=PASSWORD, device=DEVICE)
    old = first.data["data"]["refresh_token"]
    api.post("/api/v1/auth/refresh", {"refresh_token": old}, format="json")
    reuse = api.post("/api/v1/auth/refresh", {"refresh_token": old}, format="json")
    assert reuse.status_code == 401
    assert reuse.data["code"] == "FORCE_LOGOUT"
    assert Session.objects.filter(user=user_ok, is_active=True).count() == 0


@pytest.mark.django_db
def test_refresh_unknown_no_kill(api, user_ok):
    _jwt(api, user_ok)
    r = api.post("/api/v1/auth/refresh", {"refresh_token": "not-a-real-token"}, format="json")
    assert r.status_code == 401
    assert r.data["code"] == "INVALID_REFRESH"
    assert Session.objects.filter(user=user_ok, is_active=True).count() == 1


@pytest.mark.django_db
def test_refresh_after_session_absolute_expiry(api, user_ok):
    first = login_until_jwt(api, email=user_ok.email, password=PASSWORD, device=DEVICE)
    raw = first.data["data"]["refresh_token"]
    session = Session.objects.get(user=user_ok, is_active=True)
    session.expires_at = timezone.now() - timedelta(seconds=1)
    session.last_activity = timezone.now()
    session.save(update_fields=["expires_at", "last_activity", "updated_at"])
    r = api.post("/api/v1/auth/refresh", {"refresh_token": raw}, format="json")
    assert r.status_code == 401
    assert r.data["code"] == "INVALID_REFRESH"


@pytest.mark.django_db
def test_logout_current_keeps_other_device(api, user_ok):
    first = _jwt(api, user_ok, device=DEVICE)
    token1 = first.data["data"]["access_token"]
    _jwt(api, user_ok, device=DEVICE2)
    s2 = Session.objects.get(user=user_ok, is_active=True, device__device_uuid="test-web-2")
    r = api.post("/api/v1/auth/logout", {}, format="json")
    assert r.status_code == 200
    s2.refresh_from_db()
    assert s2.is_active is False
    assert s2.revoke_reason == "LOGOUT"
    other = Session.objects.get(user=user_ok, is_active=True)
    assert other.device.device_uuid == "test-web-1"
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {token1}")
    me = api.get("/api/v1/me/")
    assert me.status_code == 200


@pytest.mark.django_db
def test_logout_then_same_access_401(api, user_ok):
    first = _jwt(api, user_ok)
    token = first.data["data"]["access_token"]
    session = Session.objects.get(user=user_ok, is_active=True)
    assert jti_blocked(session.access_jti) is False
    r = api.post("/api/v1/auth/logout", {}, format="json")
    assert r.status_code == 200
    session.refresh_from_db()
    assert jti_blocked(session.access_jti) is True
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    me = api.get("/api/v1/me/")
    assert me.status_code == 401


@pytest.mark.django_db
def test_logout_all(api, user_ok):
    _jwt(api, user_ok, device=DEVICE)
    _jwt(api, user_ok, device=DEVICE2)
    assert Session.objects.filter(user=user_ok, is_active=True).count() == 2
    r = api.post("/api/v1/auth/logout-all", {}, format="json")
    assert r.status_code == 200
    assert Session.objects.filter(user=user_ok, is_active=True).count() == 0
    assert RefreshToken.objects.filter(user=user_ok, revoked_at__isnull=True).count() == 0


@pytest.mark.django_db
def test_list_sessions_is_current_no_secrets(api, user_ok):
    _jwt(api, user_ok, device=DEVICE)
    _jwt(api, user_ok, device=DEVICE2)
    r = api.get("/api/v1/me/sessions")
    assert r.status_code == 200
    rows = r.data["data"]["sessions"]
    assert len(rows) == 2
    current = [s for s in rows if s["is_current"]]
    assert len(current) == 1
    blob = str(r.data)
    assert "refresh_hash" not in blob
    assert "access_jti" not in blob
    assert current[0]["device_name"] == "Tel lab"


@pytest.mark.django_db
def test_logout_remote_session(api, user_ok):
    _jwt(api, user_ok, device=DEVICE)
    remote = Session.objects.get(user=user_ok, is_active=True)
    _jwt(api, user_ok, device=DEVICE2)
    r = api.post(f"/api/v1/me/sessions/{remote.id}/logout", {}, format="json")
    assert r.status_code == 200
    remote.refresh_from_db()
    assert remote.is_active is False
    assert Session.objects.filter(user=user_ok, is_active=True).count() == 1


@pytest.mark.django_db
def test_logout_other_user_session_404(api, user_ok, other_user):
    _jwt(api, other_user)
    foreign = Session.objects.get(user=other_user, is_active=True)
    _jwt(api, user_ok)
    r = api.post(f"/api/v1/me/sessions/{foreign.id}/logout", {}, format="json")
    assert r.status_code == 404
    assert _body(r)["code"] == "NOT_FOUND"
    foreign.refresh_from_db()
    assert foreign.is_active is True
    missing = api.post(f"/api/v1/me/sessions/{uuid4()}/logout", {}, format="json")
    assert missing.status_code == 404


@pytest.mark.django_db
def test_logout_device_keeps_push_and_trusted(api, user_ok):
    _jwt(api, user_ok, device=DEVICE)
    _jwt(api, user_ok, device=DEVICE2)
    device2 = Device.objects.get(user=user_ok, device_uuid="test-web-2")
    device2.trusted = True
    device2.push_token = "fcm-keep"
    device2.save(update_fields=["trusted", "push_token", "updated_at"])
    r = api.post(f"/api/v1/me/devices/{device2.id}/logout", {}, format="json")
    assert r.status_code == 200
    device2.refresh_from_db()
    assert device2.trusted is True
    assert device2.push_token == "fcm-keep"
    assert Session.objects.filter(device=device2, is_active=True).count() == 0
    assert Session.objects.filter(user=user_ok, is_active=True).count() == 1


@pytest.mark.django_db
def test_idle_jwt_401_then_job_inactivity(api, user_ok):
    _jwt(api, user_ok)
    session = Session.objects.get(user=user_ok, is_active=True)
    session.last_activity = timezone.now() - timedelta(days=8)
    session.save(update_fields=["last_activity", "updated_at"])
    me = api.get("/api/v1/me/")
    assert me.status_code == 401
    session.refresh_from_db()
    assert session.is_active is True
    n = reap_sessions()
    assert n >= 1
    session.refresh_from_db()
    assert session.is_active is False
    assert session.revoke_reason == "INACTIVITY"


@pytest.mark.django_db
def test_absolute_expiry_jwt_401_then_job_expired(api, user_ok):
    _jwt(api, user_ok)
    session = Session.objects.get(user=user_ok, is_active=True)
    session.expires_at = timezone.now() - timedelta(seconds=1)
    session.last_activity = timezone.now()
    session.save(update_fields=["expires_at", "last_activity", "updated_at"])
    me = api.get("/api/v1/me/")
    assert me.status_code == 401
    n = reap_sessions()
    assert n >= 1
    session.refresh_from_db()
    assert session.is_active is False
    assert session.revoke_reason == "EXPIRED"


@pytest.mark.django_db
def test_heartbeat_debounce_and_no_presence(api, user_ok):
    _jwt(api, user_ok)
    session = Session.objects.get(user=user_ok, is_active=True)
    status_before = user_ok.status
    session.last_activity = timezone.now() - timedelta(seconds=61)
    session.save(update_fields=["last_activity", "updated_at"])
    r1 = api.post("/api/v1/me/sessions/current/heartbeat", {}, format="json")
    assert r1.status_code == 200
    t1 = r1.data["data"]["last_activity"]
    session.refresh_from_db()
    written = session.last_activity
    r2 = api.post("/api/v1/me/sessions/current/heartbeat", {}, format="json")
    assert r2.status_code == 200
    session.refresh_from_db()
    assert session.last_activity == written
    assert r2.data["data"]["last_activity"] == t1
    user_ok.refresh_from_db()
    assert user_ok.status == status_before


@pytest.mark.django_db
def test_logout_allowed_while_tos_open(api, user_fresh):
    _jwt(api, user_fresh)
    listed = api.get("/api/v1/me/sessions")
    assert listed.status_code == 200
    devices = api.get("/api/v1/me/devices")
    assert devices.status_code == 403
    assert _body(devices)["code"] == "TOS_REQUIRED"
    r = api.post("/api/v1/auth/logout", {}, format="json")
    assert r.status_code == 200


@pytest.mark.django_db
def test_auth_g_reset_still_kills_sessions(api, user_ok):
    _jwt(api, user_ok)
    ticket = api.post(
        "/api/v1/auth/password/reset/verify",
        {"email": user_ok.email, "otp": totp_now(user_ok)},
        format="json",
    ).data["data"]["reset_token"]
    api.credentials()
    api.post(
        "/api/v1/auth/password/reset",
        {"reset_token": ticket, "new_password": NEW_PASSWORD},
        format="json",
    )
    assert Session.objects.filter(user=user_ok, is_active=True).count() == 0


@pytest.mark.django_db
def test_health_and_docs(api, db):
    assert api.get("/health").status_code == 200
    assert api.get("/api/docs/").status_code == 200
    schema = api.get("/api/schema/").content.decode()
    assert "/api/v1/auth/logout" in schema
    assert "/api/v1/auth/logout-all" in schema
    assert "/api/v1/me/sessions" in schema
    assert "heartbeat" in schema
