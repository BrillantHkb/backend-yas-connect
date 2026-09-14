"""PROF-C : GET/PATCH /me/privacy, effet immédiat 23–25, ≠ souhaits PROF-B."""

import pytest
from django.conf import settings
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework.test import APIClient

from apps.annuaire.models import Segment, SegmentType
from apps.iam.helpers.compliance import close_gates
from apps.iam.helpers.mfa import login_until_jwt
from apps.iam.models import AuditLog, Role, RolePermission, User
from apps.iam.services.presence_service import set_live
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
def media_root(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    return tmp_path


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
    user = close_gates(
        User.objects.create_user(
            email="marie.koevi@yas.tg",
            password=PASSWORD,
            username="marie.koevi",
            role=user_role,
            first_name="Marie",
            last_name="Koevi",
        )
    )
    user.last_login = timezone.now()
    user.status = User.PresenceStatus.ONLINE
    user.save(update_fields=["last_login", "status", "updated_at"])
    return user


def _jwt(api, user, *, password=PASSWORD, device=DEVICE):
    r = login_until_jwt(api, email=user.email, password=password, device=device)
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {r.data['data']['access_token']}")
    return r


def _jpeg(size=100_000, content_type="image/jpeg", name="avatar.jpg"):
    payload = b"\xff\xd8\xff\xd9" + b"\x00" * max(0, size - 4)
    return SimpleUploadedFile(name, payload, content_type=content_type)


def _same_segment(jean, marie):
    st = SegmentType.objects.create(code="SERVICE", name="Service", level=2)
    noc = Segment.objects.create(code="NOC", name="NOC", segment_type=st, is_active=True)
    jean.segment_id = noc.id
    jean.save(update_fields=["segment_id", "updated_at"])
    marie.segment_id = noc.id
    marie.save(update_fields=["segment_id", "updated_at"])
    return noc


@pytest.mark.django_db
def test_get_privacy_defaults(api, jean):
    _jwt(api, jean)
    r = api.get("/api/v1/me/privacy")
    assert r.status_code == 200
    data = r.data["data"]
    assert data["last_seen_visibility"] == "EVERYONE"
    assert data["profile_photo_visibility"] == "EVERYONE"
    assert data["online_status_visibility"] == "EVERYONE"
    assert data["read_receipts_enabled"] is True
    assert data["typing_indicator_enabled"] is True
    assert data["allow_calls"] is True
    assert data["allow_mentions"] is True
    assert data["allow_group_invites"] is True
    assert data["updated_at"] is not None


@pytest.mark.django_db
def test_patch_last_seen_nobody_hides_from_colleague(api, jean, marie):
    _jwt(api, marie)
    r = api.patch("/api/v1/me/privacy", {"last_seen_visibility": "NOBODY"}, format="json")
    assert r.status_code == 200
    assert r.data["data"]["last_seen_visibility"] == "NOBODY"
    me = api.get("/api/v1/me/")
    assert me.status_code == 200
    assert me.data["data"]["user"]["last_seen"] is not None
    _jwt(api, jean)
    col = api.get(f"/api/v1/users/{marie.id}")
    assert col.status_code == 200
    assert col.data["data"]["user"]["last_seen"] is None


@pytest.mark.django_db
def test_patch_last_seen_contacts_same_segment(api, jean, marie):
    _same_segment(jean, marie)
    _jwt(api, marie)
    assert api.patch(
        "/api/v1/me/privacy", {"last_seen_visibility": "CONTACTS"}, format="json"
    ).status_code == 200
    _jwt(api, jean)
    r = api.get(f"/api/v1/users/{marie.id}")
    assert r.status_code == 200
    assert r.data["data"]["user"]["last_seen"] is not None


@pytest.mark.django_db
def test_patch_last_seen_contacts_other_segment(api, jean, marie):
    st = SegmentType.objects.create(code="SERVICE", name="Service", level=2)
    a = Segment.objects.create(code="NOC", name="NOC", segment_type=st, is_active=True)
    b = Segment.objects.create(code="RH", name="RH", segment_type=st, is_active=True)
    jean.segment_id = a.id
    jean.save(update_fields=["segment_id", "updated_at"])
    marie.segment_id = b.id
    marie.save(update_fields=["segment_id", "updated_at"])
    _jwt(api, marie)
    assert api.patch(
        "/api/v1/me/privacy", {"last_seen_visibility": "CONTACTS"}, format="json"
    ).status_code == 200
    _jwt(api, jean)
    r = api.get(f"/api/v1/users/{marie.id}")
    assert r.status_code == 200
    assert r.data["data"]["user"]["last_seen"] is None


@pytest.mark.django_db
def test_patch_photo_nobody_hides_avatar(api, jean, marie, media_root):
    _jwt(api, marie)
    up = api.post("/api/v1/me/avatar", {"file": _jpeg()}, format="multipart")
    assert up.status_code == 200
    assert api.patch(
        "/api/v1/me/privacy", {"profile_photo_visibility": "NOBODY"}, format="json"
    ).status_code == 200
    me = api.get("/api/v1/me/")
    assert me.data["data"]["user"]["avatar_url"] is not None
    _jwt(api, jean)
    r = api.get(f"/api/v1/users/{marie.id}")
    assert r.status_code == 200
    assert r.data["data"]["user"]["avatar_url"] is None


@pytest.mark.django_db
def test_patch_online_nobody_status_null(api, jean, marie):
    _jwt(api, marie)
    assert api.patch(
        "/api/v1/me/privacy", {"online_status_visibility": "NOBODY"}, format="json"
    ).status_code == 200
    set_live(marie)
    me = api.get("/api/v1/me/")
    assert me.status_code == 200
    assert me.data["data"]["user"]["status"] == User.PresenceStatus.ONLINE
    _jwt(api, jean)
    r = api.get(f"/api/v1/users/{marie.id}")
    assert r.status_code == 200
    assert r.data["data"]["user"]["status"] is None


@pytest.mark.django_db
def test_patch_visibility_typo_everyone(api, jean):
    _jwt(api, jean)
    r = api.patch("/api/v1/me/privacy", {"last_seen_visibility": "everyone"}, format="json")
    assert r.status_code == 400
    assert r.data["code"] == "INVALID_VISIBILITY"


@pytest.mark.django_db
def test_patch_read_receipts_enabled_leaves_prefs(api, jean):
    before = jean.preferences.read_receipts
    _jwt(api, jean)
    r = api.patch("/api/v1/me/privacy", {"read_receipts_enabled": False}, format="json")
    assert r.status_code == 200
    assert r.data["data"]["read_receipts_enabled"] is False
    jean.preferences.refresh_from_db()
    assert jean.preferences.read_receipts == before


@pytest.mark.django_db
def test_patch_typing_enabled_leaves_prefs(api, jean):
    before = jean.preferences.typing_indicator
    _jwt(api, jean)
    r = api.patch("/api/v1/me/privacy", {"typing_indicator_enabled": False}, format="json")
    assert r.status_code == 200
    assert r.data["data"]["typing_indicator_enabled"] is False
    jean.preferences.refresh_from_db()
    assert jean.preferences.typing_indicator == before


@pytest.mark.django_db
def test_patch_allow_flags_persisted(api, jean):
    _jwt(api, jean)
    r = api.patch(
        "/api/v1/me/privacy",
        {
            "allow_calls": False,
            "allow_mentions": False,
            "allow_group_invites": False,
        },
        format="json",
    )
    assert r.status_code == 200
    data = r.data["data"]
    assert data["allow_calls"] is False
    assert data["allow_mentions"] is False
    assert data["allow_group_invites"] is False
    again = api.get("/api/v1/me/privacy")
    assert again.data["data"]["allow_calls"] is False


@pytest.mark.django_db
def test_patch_prefs_key_unknown_field(api, jean):
    _jwt(api, jean)
    r = api.patch("/api/v1/me/privacy", {"read_receipts": False}, format="json")
    assert r.status_code == 400
    assert r.data["code"] == "UNKNOWN_FIELD"


@pytest.mark.django_db
def test_patch_bool_string_validation_error(api, jean):
    _jwt(api, jean)
    r = api.patch("/api/v1/me/privacy", {"allow_calls": "0"}, format="json")
    assert r.status_code == 400
    assert r.data["code"] == "VALIDATION_ERROR"


@pytest.mark.django_db
def test_privacy_patch_audits(api, jean):
    _jwt(api, jean)
    api.patch("/api/v1/me/privacy", {"allow_calls": False}, format="json")
    assert AuditLog.objects.filter(action="PRIVACY_PATCH", user=jean).exists()


@pytest.mark.django_db
def test_privacy_before_wizard_403(api, user_role):
    fresh = User.objects.create_user(
        email="neuf@yas.tg",
        password=PASSWORD,
        username="user.neuf",
        role=user_role,
        first_name="Neuf",
        last_name="Compte",
    )
    _jwt(api, fresh)
    blocked = api.get("/api/v1/me/privacy")
    assert blocked.status_code == 403
    assert blocked.data["code"] == "TOS_REQUIRED"
    api.post("/api/v1/me/tos/accept", {"version": settings.YAS_TOS_VERSION}, format="json")
    r = api.get("/api/v1/me/privacy")
    assert r.status_code == 403
    assert r.data["code"] == "ONBOARDING_REQUIRED"


@pytest.mark.django_db
def test_colleague_has_no_privacy_sheet(api, jean, marie):
    _jwt(api, jean)
    r = api.get(f"/api/v1/users/{marie.id}")
    assert r.status_code == 200
    user = r.data["data"]["user"]
    assert "privacy" not in user
    assert "gates" not in r.data["data"]


@pytest.mark.django_db
def test_privacy_update_forbidden_without_perm(api, jean):
    RolePermission.objects.filter(role=jean.role, permission__code="iam.privacy.update").delete()
    invalidate_role_cache(jean.role_id)
    _jwt(api, jean)
    r = api.patch("/api/v1/me/privacy", {"allow_calls": False}, format="json")
    assert r.status_code == 403
    assert r.data["code"] == "FORBIDDEN"
    assert r.data["permission"] == "iam.privacy.update"


@pytest.mark.django_db
def test_privacy_without_jwt_401(api, jean):
    r = api.get("/api/v1/me/privacy")
    assert r.status_code == 401


@pytest.mark.django_db
def test_schema_has_privacy(api, db):
    assert api.get("/health").status_code == 200
    schema = api.get("/api/schema/")
    assert schema.status_code == 200
    text = schema.content.decode()
    assert "/api/v1/me/privacy" in text
    assert api.get("/api/docs/").status_code == 200


@pytest.mark.django_db
def test_me_still_has_privacy_block(api, jean):
    _jwt(api, jean)
    r = api.get("/api/v1/me/")
    assert r.status_code == 200
    assert "privacy" in r.data["data"]["user"]
    assert "updated_at" not in r.data["data"]["user"]["privacy"]
