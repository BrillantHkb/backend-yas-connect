"""AUTH-E : appareils, push, trusted, jailbreak, revoke / compromise."""

import pytest
from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APIClient

from apps.iam.helpers.mfa import login_until_jwt, post_mfa_verify
from apps.iam.models import AuditLog, Device, LoginHistory, Role, Session, User

DEVICE = {"device_uuid": "test-web-1", "platform": "WEB", "model": "Pixel"}
DEVICE2 = {"device_uuid": "test-web-2", "platform": "WEB"}
UA = "Mozilla/5.0 pytest"
PASSWORD = "Secret123!"
ADMIN_PASSWORD = "Admin123!"


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
def admin_role(db):
    return Role.objects.create(code="ADMIN", name="Administrateur", is_system=True, level=100)


@pytest.fixture
def user_ok(role):
    return User.objects.create_user(
        email="jean.dupont@yas.tg",
        password=PASSWORD,
        username="jean.dupont",
        role=role,
        first_name="Jean",
        last_name="Dupont",
    )


@pytest.fixture
def admin_ok(admin_role):
    return User.objects.create_user(
        email="admin@yas.tg",
        password=ADMIN_PASSWORD,
        username="admin.yas",
        role=admin_role,
        first_name="Admin",
        last_name="YAS",
    )


@pytest.fixture
def other_user(role):
    return User.objects.create_user(
        email="marie@yas.tg",
        password=PASSWORD,
        username="marie.koevi",
        role=role,
    )


def _bearer(api, token):
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")


def _login_jwt(api, user, device=DEVICE, password=PASSWORD):
    return login_until_jwt(api, email=user.email, password=password, device=device)


@pytest.mark.django_db
def test_first_login_creates_device(api, user_ok):
    _login_jwt(api, user_ok)
    device = Device.objects.get(user=user_ok)
    assert device.platform == "WEB"
    assert device.model == "Pixel"
    assert Device.objects.filter(user=user_ok).count() == 1
    hist = LoginHistory.objects.get(success=True)
    assert hist.suspicious is True
    assert AuditLog.objects.filter(action="DEVICE_NEW", entity_id=device.id).exists()


@pytest.mark.django_db
def test_second_login_same_uuid(api, user_ok):
    _login_jwt(api, user_ok)
    first = Device.objects.get(user=user_ok)
    seen = first.last_seen
    _login_jwt(api, user_ok)
    assert Device.objects.filter(user=user_ok).count() == 1
    first.refresh_from_db()
    assert first.last_seen >= seen
    last = LoginHistory.objects.filter(success=True).order_by("-created_at").first()
    assert last.suspicious is False


@pytest.mark.django_db
def test_patch_current_push_token_hidden_on_get(api, user_ok):
    tok = _login_jwt(api, user_ok).data["data"]["access_token"]
    _bearer(api, tok)
    r = api.patch(
        "/api/v1/me/devices/current",
        {"push_token": "fcm-secret-token", "app_version": "1.4.3"},
        format="json",
    )
    assert r.status_code == 200
    listed = api.get("/api/v1/me/devices")
    assert listed.status_code == 200
    row = listed.data["data"]["devices"][0]
    assert "push_token" not in row
    assert row["is_current"] is True
    assert row["app_version"] == "1.4.3"
    assert Device.objects.get(user=user_ok).push_token == "fcm-secret-token"


@pytest.mark.django_db
def test_trusted_still_mfa(api, user_ok):
    tok = _login_jwt(api, user_ok).data["data"]["access_token"]
    device = Device.objects.get(user=user_ok)
    _bearer(api, tok)
    ok = api.patch(f"/api/v1/me/devices/{device.id}", {"trusted": True}, format="json")
    assert ok.status_code == 200
    assert ok.data["data"]["trusted"] is True
    api.credentials()
    r = api.post(
        "/api/v1/auth/login",
        {"email": user_ok.email, "password": PASSWORD, "device": DEVICE},
        format="json",
    )
    assert r.status_code == 200
    assert r.data["data"]["mfa_required"] is True
    assert "access_token" not in r.data["data"]


@pytest.mark.django_db
def test_untrust_keeps_session(api, user_ok):
    tok = _login_jwt(api, user_ok).data["data"]["access_token"]
    device = Device.objects.get(user=user_ok)
    _bearer(api, tok)
    r = api.patch(f"/api/v1/me/devices/{device.id}", {"trusted": False}, format="json")
    assert r.status_code == 200
    assert Session.objects.filter(user=user_ok, is_active=True).exists()


@pytest.mark.django_db
def test_ios_jailbreak_blocked(api, user_ok):
    ios = {"device_uuid": "iphone-1", "platform": "IOS", "jailbreak": True}
    r = api.post(
        "/api/v1/auth/login",
        {"email": user_ok.email, "password": PASSWORD, "device": ios},
        format="json",
    )
    v = post_mfa_verify(api, mfa_token=r.data["data"]["mfa_token"], user=user_ok)
    assert v.status_code == 403
    assert v.data["code"] == "DEVICE_JAILBROKEN"
    rec = Device.objects.get(user=user_ok, device_uuid="iphone-1")
    assert rec.jailbreak is True
    assert not Session.objects.filter(user=user_ok, is_active=True).exists()


@pytest.mark.django_db
def test_web_jailbreak_allowed(api, user_ok):
    web = {**DEVICE, "jailbreak": True}
    v = _login_jwt(api, user_ok, device=web)
    assert v.status_code == 200
    assert Device.objects.get(user=user_ok).jailbreak is True
    assert Session.objects.filter(user=user_ok, is_active=True).exists()


@pytest.mark.django_db
@override_settings(YAS_BLOCK_JAILBREAK=False)
def test_android_jailbreak_when_policy_off(api, user_ok):
    android = {"device_uuid": "and-1", "platform": "ANDROID", "jailbreak": True}
    v = _login_jwt(api, user_ok, device=android)
    assert v.status_code == 200
    assert Device.objects.get(user=user_ok).jailbreak is True


@pytest.mark.django_db
def test_compromise_other_device(api, user_ok):
    _login_jwt(api, user_ok, device=DEVICE)
    tok2 = _login_jwt(api, user_ok, device=DEVICE2).data["data"]["access_token"]
    other = Device.objects.get(user=user_ok, device_uuid="test-web-1")
    _bearer(api, tok2)
    r = api.post(f"/api/v1/me/devices/{other.id}/compromise")
    assert r.status_code == 200
    other.refresh_from_db()
    assert other.compromised is True
    api.credentials()
    login = api.post(
        "/api/v1/auth/login",
        {"email": user_ok.email, "password": PASSWORD, "device": DEVICE},
        format="json",
    )
    v = post_mfa_verify(api, mfa_token=login.data["data"]["mfa_token"], user=user_ok)
    assert v.status_code == 403
    assert v.data["code"] == "DEVICE_COMPROMISED"


@pytest.mark.django_db
def test_compromise_current_400(api, user_ok):
    tok = _login_jwt(api, user_ok).data["data"]["access_token"]
    device = Device.objects.get(user=user_ok)
    _bearer(api, tok)
    r = api.post(f"/api/v1/me/devices/{device.id}/compromise")
    assert r.status_code == 400
    assert r.data["code"] == "CANNOT_COMPROMISE_CURRENT"


@pytest.mark.django_db
def test_revoke_then_relogin_ok(api, user_ok):
    tok = _login_jwt(api, user_ok).data["data"]["access_token"]
    device = Device.objects.get(user=user_ok)
    _bearer(api, tok)
    r = api.post(f"/api/v1/me/devices/{device.id}/revoke")
    assert r.status_code == 200
    assert not Session.objects.filter(user=user_ok, is_active=True).exists()
    api.credentials()
    again = _login_jwt(api, user_ok)
    assert again.status_code == 200
    device.refresh_from_db()
    assert device.compromised is False


@pytest.mark.django_db
def test_list_is_current_not_others(api, user_ok, other_user):
    tok = _login_jwt(api, user_ok).data["data"]["access_token"]
    _login_jwt(api, other_user)
    _bearer(api, tok)
    listed = api.get("/api/v1/me/devices")
    uuids = {row["device_uuid"] for row in listed.data["data"]["devices"]}
    assert uuids == {"test-web-1"}
    assert listed.data["data"]["devices"][0]["is_current"] is True


@pytest.mark.django_db
def test_patch_name(api, user_ok):
    tok = _login_jwt(api, user_ok).data["data"]["access_token"]
    device = Device.objects.get(user=user_ok)
    _bearer(api, tok)
    r = api.patch(
        f"/api/v1/me/devices/{device.id}",
        {"device_name": "iPhone perso"},
        format="json",
    )
    assert r.status_code == 200
    listed = api.get("/api/v1/me/devices")
    assert listed.data["data"]["devices"][0]["device_name"] == "iPhone perso"


@pytest.mark.django_db
def test_foreign_device_404(api, user_ok, other_user):
    _login_jwt(api, other_user)
    foreign = Device.objects.get(user=other_user)
    tok = _login_jwt(api, user_ok).data["data"]["access_token"]
    _bearer(api, tok)
    assert api.get("/api/v1/me/devices").status_code == 200
    r = api.patch(f"/api/v1/me/devices/{foreign.id}", {"trusted": True}, format="json")
    assert r.status_code == 404


@pytest.mark.django_db
def test_user_cannot_admin_compromise(api, user_ok, admin_ok):
    _login_jwt(api, admin_ok, password=ADMIN_PASSWORD)
    target = Device.objects.get(user=admin_ok)
    tok = _login_jwt(api, user_ok).data["data"]["access_token"]
    _bearer(api, tok)
    r = api.post(f"/api/v1/admin/devices/{target.id}/compromise")
    assert r.status_code == 403


@pytest.mark.django_db
def test_admin_compromise_and_clear(api, user_ok, admin_ok):
    _login_jwt(api, user_ok)
    victim = Device.objects.get(user=user_ok)
    admin_tok = _login_jwt(api, admin_ok, password=ADMIN_PASSWORD).data["data"]["access_token"]
    _bearer(api, admin_tok)
    r = api.post(f"/api/v1/admin/devices/{victim.id}/compromise")
    assert r.status_code == 200
    victim.refresh_from_db()
    assert victim.compromised is True
    clr = api.post(f"/api/v1/admin/devices/{victim.id}/clear-compromise")
    assert clr.status_code == 200
    victim.refresh_from_db()
    assert victim.compromised is False
    assert victim.trusted is False


@pytest.mark.django_db
def test_health_and_docs(api, db):
    assert api.get("/health").status_code == 200
    assert api.get("/api/docs/").status_code == 200
    schema = api.get("/api/schema/")
    text = schema.content.decode()
    assert "/api/v1/me/devices" in text
    assert "mfa/reset" in text or "/api/v1/admin/devices" in text
