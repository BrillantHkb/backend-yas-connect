"""AUTH-F : CGU + wizard. JWT après MFA ; métier bloqué tant que portes ouvertes."""

import pytest
from django.conf import settings
from django.core.cache import cache
from django.core.management import call_command
from django.test import override_settings
from rest_framework.test import APIClient

from apps.iam.helpers.mfa import login_until_jwt
from apps.iam.models import AuditLog, Role, User

DEVICE = {"device_uuid": "test-web-1", "platform": "WEB"}
UA = "Mozilla/5.0 pytest"
PASSWORD = "Secret123!"


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
def user_fresh(role):
    """Compte neuf : portes NULL (comme AUTH-D)."""
    return User.objects.create_user(
        email="neuf@yas.tg",
        password=PASSWORD,
        username="user.neuf",
        role=role,
        first_name="Neuf",
        last_name="Compte",
    )


def _body(r):
    """Middleware JsonResponse n’a pas toujours r.data DRF."""
    data = getattr(r, "data", None)
    if isinstance(data, dict):
        return data
    return r.json()


def _jwt(api, user, device=DEVICE):
    r = login_until_jwt(api, email=user.email, password=PASSWORD, device=device)
    token = r.data["data"]["access_token"]
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return r


@pytest.mark.django_db
def test_first_login_timestamp_stable(api, user_fresh):
    _jwt(api, user_fresh)
    user_fresh.refresh_from_db()
    first = user_fresh.first_login
    assert first is not None
    api.credentials()
    _jwt(api, user_fresh)
    user_fresh.refresh_from_db()
    assert user_fresh.first_login == first


@pytest.mark.django_db
def test_me_gates_open_for_new_user(api, user_fresh):
    _jwt(api, user_fresh)
    r = api.get("/api/v1/me/")
    assert r.status_code == 200
    gates = r.data["data"]["gates"]
    assert gates["tos_required"] is True
    assert gates["onboarding_required"] is True
    assert gates["tos_current_version"] == settings.YAS_TOS_VERSION
    assert gates["first_login_at"] is not None
    assert r.data["data"]["user"]["email"] == user_fresh.email


@pytest.mark.django_db
def test_devices_blocked_tos(api, user_fresh):
    _jwt(api, user_fresh)
    r = api.get("/api/v1/me/devices")
    assert r.status_code == 403
    assert _body(r)["code"] == "TOS_REQUIRED"


@pytest.mark.django_db
def test_accept_wrong_version_409(api, user_fresh):
    _jwt(api, user_fresh)
    r = api.post("/api/v1/me/tos/accept", {"version": "1999-01-01"}, format="json")
    assert r.status_code == 409
    assert r.data["code"] == "TOS_VERSION_MISMATCH"
    user_fresh.refresh_from_db()
    assert user_fresh.tos_accepted_at is None


@pytest.mark.django_db
def test_accept_then_onboarding_gate(api, user_fresh):
    _jwt(api, user_fresh)
    ok = api.post(
        "/api/v1/me/tos/accept",
        {"version": settings.YAS_TOS_VERSION},
        format="json",
    )
    assert ok.status_code == 200
    user_fresh.refresh_from_db()
    assert user_fresh.tos_accepted_at is not None
    assert user_fresh.tos_version == settings.YAS_TOS_VERSION
    assert AuditLog.objects.filter(action="TOS_ACCEPT", entity_id=user_fresh.id).exists()
    r = api.get("/api/v1/me/devices")
    assert r.status_code == 403
    assert _body(r)["code"] == "ONBOARDING_REQUIRED"


@pytest.mark.django_db
def test_complete_without_tos_403(api, user_fresh):
    _jwt(api, user_fresh)
    r = api.post("/api/v1/me/onboarding/complete", {}, format="json")
    assert r.status_code == 403
    assert _body(r)["code"] == "TOS_REQUIRED"


@pytest.mark.django_db
def test_patch_then_complete_unlocks_devices(api, user_fresh):
    _jwt(api, user_fresh)
    api.post("/api/v1/me/tos/accept", {"version": settings.YAS_TOS_VERSION}, format="json")
    wizard = api.get("/api/v1/me/onboarding")
    assert wizard.status_code == 200
    assert wizard.data["data"]["language"] == "fr"
    assert wizard.data["data"]["timezone"] == "Africa/Lome"
    assert wizard.data["data"]["notification_sound"] is True
    patched = api.patch(
        "/api/v1/me/onboarding",
        {"language": "en", "timezone": "Europe/Paris", "notification_sound": False},
        format="json",
    )
    assert patched.status_code == 200
    assert patched.data["data"]["language"] == "en"
    user_fresh.refresh_from_db()
    user_fresh.preferences.refresh_from_db()
    assert user_fresh.language == "en"
    assert user_fresh.timezone == "Europe/Paris"
    assert user_fresh.preferences.notification_sound is False
    assert user_fresh.onboarding_completed_at is None
    done = api.post("/api/v1/me/onboarding/complete", {}, format="json")
    assert done.status_code == 200
    user_fresh.refresh_from_db()
    assert user_fresh.onboarding_completed_at is not None
    assert AuditLog.objects.filter(action="ONBOARDING_COMPLETE", entity_id=user_fresh.id).exists()
    listed = api.get("/api/v1/me/devices")
    assert listed.status_code == 200
    assert "devices" in listed.data["data"]


@pytest.mark.django_db
def test_seed_jean_gates_closed(db):
    call_command("seed_iam")
    jean = User.objects.get(email="jean.dupont@yas.tg")
    assert jean.tos_accepted_at is not None
    assert jean.tos_version == settings.YAS_TOS_VERSION
    assert jean.onboarding_completed_at is not None
    admin = User.objects.get(email="admin@yas.tg")
    assert admin.tos_accepted_at is not None
    assert admin.onboarding_completed_at is not None


@pytest.mark.django_db
def test_tos_version_bump_blocks_without_rewizard(api, user_fresh):
    _jwt(api, user_fresh)
    api.post("/api/v1/me/tos/accept", {"version": settings.YAS_TOS_VERSION}, format="json")
    api.post("/api/v1/me/onboarding/complete", {}, format="json")
    user_fresh.refresh_from_db()
    onb = user_fresh.onboarding_completed_at
    with override_settings(YAS_TOS_VERSION="2026-12-01"):
        r = api.get("/api/v1/me/devices")
        assert r.status_code == 403
        assert _body(r)["code"] == "TOS_REQUIRED"
        me = api.get("/api/v1/me/")
        assert me.status_code == 200
        assert me.data["data"]["gates"]["tos_required"] is True
        assert me.data["data"]["gates"]["onboarding_required"] is False
    user_fresh.refresh_from_db()
    assert user_fresh.onboarding_completed_at == onb


@pytest.mark.django_db
def test_no_skip_mfa_endpoint(api, user_fresh):
    _jwt(api, user_fresh)
    api.post("/api/v1/me/tos/accept", {"version": settings.YAS_TOS_VERSION}, format="json")
    r = api.post("/api/v1/me/onboarding/skip-mfa", {}, format="json")
    assert r.status_code == 404


@pytest.mark.django_db
def test_health_and_docs_public(api, db):
    assert api.get("/health").status_code == 200
    assert api.get("/api/docs/").status_code == 200
    schema = api.get("/api/schema/").content.decode()
    assert "/api/v1/me/tos" in schema
    assert "/api/v1/me/onboarding" in schema


@pytest.mark.django_db
def test_heartbeat_allowed_during_tos(api, user_fresh):
    """PATCH current reste joignable (session vivante) tant que CGU KO."""
    _jwt(api, user_fresh)
    r = api.patch("/api/v1/me/devices/current", {"app_version": "1.0.0"}, format="json")
    assert r.status_code == 200
    assert r.data["success"] is True


@pytest.mark.django_db
def test_refresh_allowed_during_tos(api, user_fresh):
    login = _jwt(api, user_fresh)
    refresh = login.data["data"]["refresh_token"]
    api.credentials()  # refresh est public
    r = api.post("/api/v1/auth/refresh", {"refresh_token": refresh}, format="json")
    assert r.status_code == 200
    assert "access_token" in r.data["data"]
