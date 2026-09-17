"""GET /api/v1/config — plafonds/fenêtres publics (audit W40)."""

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.config.models import SystemSetting
from apps.iam.helpers.compliance import close_gates
from apps.iam.helpers.mfa import login_until_jwt
from apps.iam.models import Role, User

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
def user_role(db):
    return Role.objects.create(code="USER", name="Utilisateur", is_system=True, level=0)


@pytest.fixture
def user_ok(user_role):
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


def _jwt(api, user):
    r = login_until_jwt(api, email=user.email, password=PASSWORD, device=DEVICE)
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {r.data['data']['access_token']}")
    return r


@pytest.mark.django_db
def test_config_without_jwt_401(api, db):
    r = api.get("/api/v1/config")
    assert r.status_code == 401


@pytest.mark.django_db
def test_config_defaults_when_no_settings_rows(api, user_ok):
    """seed_config non exécuté -> repli Python, même valeurs que le code historique."""
    _jwt(api, user_ok)
    r = api.get("/api/v1/config")
    assert r.status_code == 200
    data = r.data["data"]
    assert data["media"]["max_image_bytes"] == 10485760
    assert data["messaging"]["edit_window_minutes"] == 15
    assert data["messaging"]["delete_window_hours"] == 48
    assert data["messaging"]["max_encrypted_content_bytes"] == 65536
    assert data["client"]["min_version"] == ""


@pytest.mark.django_db
def test_config_reads_system_setting_overrides(api, user_ok):
    SystemSetting.objects.create(
        category="messaging",
        setting_key="edit_window_minutes",
        setting_value=30,
        value_type="int",
    )
    SystemSetting.objects.create(
        category="client",
        setting_key="min_version",
        setting_value="2.0.0",
        value_type="string",
    )
    _jwt(api, user_ok)
    r = api.get("/api/v1/config")
    assert r.status_code == 200
    data = r.data["data"]
    assert data["messaging"]["edit_window_minutes"] == 30
    assert data["client"]["min_version"] == "2.0.0"
