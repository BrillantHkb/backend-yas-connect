"""PROF-B : editable, job_title gated, GET/PATCH /me/preferences, wizard JSON prefs."""

import pytest
from django.conf import settings
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.config.models import SystemSetting
from apps.iam.helpers.compliance import close_gates
from apps.iam.helpers.mfa import login_until_jwt
from apps.iam.models import AuditLog, Role, RolePermission, User
from apps.iam.services.rbac_service import invalidate_role_cache

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
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {r.data['data']['access_token']}")
    return r


def _set_job_title_flag(value: bool):
    SystemSetting.objects.update_or_create(
        category="profile",
        setting_key="job_title_self_edit",
        defaults={
            "setting_value": value,
            "value_type": "bool",
            "is_sensitive": False,
            "editable": True,
        },
    )


@pytest.mark.django_db
def test_me_editable_defaults(api, jean):
    _jwt(api, jean)
    r = api.get("/api/v1/me/")
    assert r.status_code == 200
    editable = r.data["data"]["user"]["editable"]
    assert editable["phone"] is True
    assert editable["matricule"] is False
    assert editable["job_title"] is False
    assert editable["first_name"] is True
    assert "preferences" in r.data["data"]["user"]
    assert "privacy" in r.data["data"]["user"]
    assert "role" not in r.data["data"]["user"]


@pytest.mark.django_db
def test_patch_phone_still_ok(api, jean):
    _jwt(api, jean)
    r = api.patch("/api/v1/me/", {"phone": "+22890123456"}, format="json")
    assert r.status_code == 200
    assert r.data["data"]["user"]["phone"] == "+22890123456"


@pytest.mark.django_db
def test_patch_job_title_forbidden_has_field(api, jean):
    _jwt(api, jean)
    r = api.patch("/api/v1/me/", {"job_title": "Ingénieur NOC"}, format="json")
    assert r.status_code == 400
    assert r.data["code"] == "FIELD_FORBIDDEN"
    assert r.data["field"] == "job_title"


@pytest.mark.django_db
def test_patch_job_title_when_flag_true(api, jean):
    _set_job_title_flag(True)
    _jwt(api, jean)
    r = api.patch("/api/v1/me/", {"job_title": "Ingénieur NOC"}, format="json")
    assert r.status_code == 200
    assert r.data["data"]["user"]["job_title"] == "Ingénieur NOC"
    assert r.data["data"]["user"]["editable"]["job_title"] is True


@pytest.mark.django_db
def test_patch_language_on_me_forbidden(api, jean):
    _jwt(api, jean)
    r = api.patch("/api/v1/me/", {"language": "en"}, format="json")
    assert r.status_code == 400
    assert r.data["code"] == "FIELD_FORBIDDEN"


@pytest.mark.django_db
def test_patch_prefs_language_en_aligns_user(api, jean):
    _jwt(api, jean)
    r = api.patch("/api/v1/me/preferences", {"language": "en"}, format="json")
    assert r.status_code == 200
    assert r.data["data"]["language"] == "en"
    jean.refresh_from_db()
    jean.preferences.refresh_from_db()
    assert jean.language == "en"
    assert jean.preferences.language == "en"
    assert AuditLog.objects.filter(action="PREFS_PATCH").exists()


@pytest.mark.django_db
def test_patch_prefs_language_de_invalid(api, jean):
    _jwt(api, jean)
    r = api.patch("/api/v1/me/preferences", {"language": "de"}, format="json")
    assert r.status_code == 400
    assert r.data["code"] == "INVALID_LANGUAGE"


@pytest.mark.django_db
def test_patch_prefs_timezone_ok(api, jean):
    _jwt(api, jean)
    r = api.patch("/api/v1/me/preferences", {"timezone": "Europe/Paris"}, format="json")
    assert r.status_code == 200
    assert r.data["data"]["timezone"] == "Europe/Paris"
    jean.refresh_from_db()
    assert jean.timezone == "Europe/Paris"


@pytest.mark.django_db
def test_patch_prefs_timezone_invalid(api, jean):
    _jwt(api, jean)
    r = api.patch("/api/v1/me/preferences", {"timezone": "Not/AZone"}, format="json")
    assert r.status_code == 400
    assert r.data["code"] == "INVALID_TIMEZONE"


@pytest.mark.django_db
def test_patch_prefs_notification_sound(api, jean):
    _jwt(api, jean)
    r = api.patch("/api/v1/me/preferences", {"notification_sound": False}, format="json")
    assert r.status_code == 200
    assert r.data["data"]["notification_sound"] is False


@pytest.mark.django_db
def test_patch_prefs_auto_download(api, jean):
    _jwt(api, jean)
    r = api.patch("/api/v1/me/preferences", {"auto_download_media": True}, format="json")
    assert r.status_code == 200
    assert r.data["data"]["auto_download_media"] is True


@pytest.mark.django_db
def test_patch_prefs_read_receipts_leaves_privacy(api, jean):
    before = jean.privacy.read_receipts_enabled
    _jwt(api, jean)
    r = api.patch("/api/v1/me/preferences", {"read_receipts": False}, format="json")
    assert r.status_code == 200
    assert r.data["data"]["read_receipts"] is False
    jean.privacy.refresh_from_db()
    assert jean.privacy.read_receipts_enabled == before


@pytest.mark.django_db
def test_patch_prefs_typing_leaves_privacy(api, jean):
    before = jean.privacy.typing_indicator_enabled
    _jwt(api, jean)
    r = api.patch("/api/v1/me/preferences", {"typing_indicator": False}, format="json")
    assert r.status_code == 200
    assert r.data["data"]["typing_indicator"] is False
    jean.privacy.refresh_from_db()
    assert jean.privacy.typing_indicator_enabled == before


@pytest.mark.django_db
def test_patch_prefs_unknown_field(api, jean):
    _jwt(api, jean)
    r = api.patch("/api/v1/me/preferences", {"theme": "dark"}, format="json")
    assert r.status_code == 400
    assert r.data["code"] == "UNKNOWN_FIELD"


@pytest.mark.django_db
def test_onboarding_get_same_as_prefs_defaults(api, user_role):
    fresh = User.objects.create_user(
        email="neuf@yas.tg",
        password=PASSWORD,
        username="user.neuf",
        role=user_role,
        first_name="Neuf",
        last_name="Compte",
    )
    _jwt(api, fresh)
    api.post("/api/v1/me/tos/accept", {"version": settings.YAS_TOS_VERSION}, format="json")
    r = api.get("/api/v1/me/onboarding")
    assert r.status_code == 200
    data = r.data["data"]
    assert data["language"] == "fr"
    assert data["timezone"] == "Africa/Lome"
    assert data["notification_sound"] is True
    assert data["auto_download_media"] is False
    assert data["read_receipts"] is True
    assert data["typing_indicator"] is True
    assert data["last_updated"] is not None


@pytest.mark.django_db
def test_onboarding_prerempli_en(api, user_role):
    fresh = User.objects.create_user(
        email="neuf@yas.tg",
        password=PASSWORD,
        username="user.neuf",
        role=user_role,
        first_name="Neuf",
        last_name="Compte",
        language="en",
    )
    fresh.preferences.language = "en"
    fresh.preferences.save()
    _jwt(api, fresh)
    api.post("/api/v1/me/tos/accept", {"version": settings.YAS_TOS_VERSION}, format="json")
    r = api.get("/api/v1/me/onboarding")
    assert r.status_code == 200
    assert r.data["data"]["language"] == "en"


@pytest.mark.django_db
def test_prefs_before_wizard_403(api, user_role):
    fresh = User.objects.create_user(
        email="neuf@yas.tg",
        password=PASSWORD,
        username="user.neuf",
        role=user_role,
        first_name="Neuf",
        last_name="Compte",
    )
    _jwt(api, fresh)
    blocked = api.get("/api/v1/me/preferences")
    assert blocked.status_code == 403
    assert blocked.data["code"] == "TOS_REQUIRED"
    api.post("/api/v1/me/tos/accept", {"version": settings.YAS_TOS_VERSION}, format="json")
    r = api.get("/api/v1/me/preferences")
    assert r.status_code == 403
    assert r.data["code"] == "ONBOARDING_REQUIRED"


@pytest.mark.django_db
def test_colleague_has_no_prefs_nor_editable(api, jean, marie):
    _jwt(api, jean)
    r = api.get(f"/api/v1/users/{marie.id}")
    assert r.status_code == 200
    user = r.data["data"]["user"]
    assert "preferences" not in user
    assert "editable" not in user


@pytest.mark.django_db
def test_prefs_update_forbidden_without_perm(api, jean):
    RolePermission.objects.filter(role=jean.role, permission__code="iam.prefs.update").delete()
    invalidate_role_cache(jean.role_id)
    _jwt(api, jean)
    r = api.patch("/api/v1/me/preferences", {"language": "en"}, format="json")
    assert r.status_code == 403
    assert r.data["code"] == "FORBIDDEN"
    assert r.data["permission"] == "iam.prefs.update"


@pytest.mark.django_db
def test_prefs_without_jwt_401(api, jean):
    r = api.get("/api/v1/me/preferences")
    assert r.status_code == 401


@pytest.mark.django_db
def test_schema_has_preferences(api, db):
    assert api.get("/health").status_code == 200
    schema = api.get("/api/schema/")
    assert schema.status_code == 200
    text = schema.content.decode()
    assert "/api/v1/me/preferences" in text
    assert api.get("/api/docs/").status_code == 200
