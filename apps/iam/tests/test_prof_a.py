"""PROF-A : fiche /me, PATCH, collègue, avatar, org."""

from uuid import uuid4

import pytest
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework.test import APIClient

from apps.annuaire.models import Segment, SegmentType
from apps.iam.helpers.compliance import close_gates
from apps.iam.helpers.mfa import login_until_jwt
from apps.iam.models import AuditLog, Region, Role, RolePermission, User, Visibility
from apps.iam.services.rbac_service import invalidate_role_cache
from apps.media.models import MediaFile

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


def _jpeg(size=100_000, content_type="image/jpeg", name="avatar.jpg"):
    payload = b"\xff\xd8\xff\xd9" + b"\x00" * max(0, size - 4)
    return SimpleUploadedFile(name, payload, content_type=content_type)


@pytest.mark.django_db
def test_get_me_no_role_org_null(api, jean):
    _jwt(api, jean)
    r = api.get("/api/v1/me/")
    assert r.status_code == 200
    user = r.data["data"]["user"]
    assert user["display_name"] == "Jean Dupont"
    assert user["org"] is None
    assert "role" not in user
    assert "role_id" not in user
    assert "role_code" not in user
    assert "gates" in r.data["data"]
    assert "preferences" in user
    assert "privacy" in user


@pytest.mark.django_db
def test_patch_me_blocked_tos(api, user_role):
    fresh = User.objects.create_user(
        email="neuf@yas.tg",
        password=PASSWORD,
        username="user.neuf",
        role=user_role,
        first_name="Neuf",
        last_name="Compte",
    )
    _jwt(api, fresh)
    r = api.patch("/api/v1/me/", {"first_name": "X"}, format="json")
    assert r.status_code == 403
    assert r.data["code"] == "TOS_REQUIRED"


@pytest.mark.django_db
def test_colleague_photo_nobody(api, jean, marie, media_root):
    _jwt(api, marie)
    up = api.post("/api/v1/me/avatar", {"file": _jpeg()}, format="multipart")
    assert up.status_code == 200
    priv = marie.privacy
    priv.profile_photo_visibility = Visibility.NOBODY
    priv.save(update_fields=["profile_photo_visibility", "updated_at"])
    _jwt(api, jean)
    r = api.get(f"/api/v1/users/{marie.id}")
    assert r.status_code == 200
    user = r.data["data"]["user"]
    assert user["avatar_url"] is None
    assert user["display_name"] == "Marie Koevi"
    assert user["email"] == marie.email
    assert "gates" not in r.data["data"]
    assert "email_pending" not in user
    assert "preferences" not in user


@pytest.mark.django_db
def test_colleague_contacts_other_segment_hides_photo(api, jean, marie, media_root):
    st = SegmentType.objects.create(code="SERVICE", name="Service", level=2)
    a = Segment.objects.create(code="NOC", name="NOC", segment_type=st, is_active=True)
    b = Segment.objects.create(code="RH", name="RH", segment_type=st, is_active=True)
    jean.segment_id = a.id
    jean.save(update_fields=["segment_id", "updated_at"])
    marie.segment_id = b.id
    marie.save(update_fields=["segment_id", "updated_at"])
    _jwt(api, marie)
    assert api.post("/api/v1/me/avatar", {"file": _jpeg()}, format="multipart").status_code == 200
    priv = marie.privacy
    priv.profile_photo_visibility = Visibility.CONTACTS
    priv.save(update_fields=["profile_photo_visibility", "updated_at"])
    _jwt(api, jean)
    r = api.get(f"/api/v1/users/{marie.id}")
    assert r.status_code == 200
    assert r.data["data"]["user"]["avatar_url"] is None


@pytest.mark.django_db
def test_colleague_contacts_same_segment_shows_photo(api, jean, marie, media_root):
    st = SegmentType.objects.create(code="SERVICE", name="Service", level=2)
    noc = Segment.objects.create(code="NOC", name="NOC", segment_type=st, is_active=True)
    jean.segment_id = noc.id
    jean.save(update_fields=["segment_id", "updated_at"])
    marie.segment_id = noc.id
    marie.save(update_fields=["segment_id", "updated_at"])
    _jwt(api, marie)
    up = api.post("/api/v1/me/avatar", {"file": _jpeg()}, format="multipart")
    assert up.status_code == 200
    url = up.data["data"]["avatar_url"]
    priv = marie.privacy
    priv.profile_photo_visibility = Visibility.CONTACTS
    priv.save(update_fields=["profile_photo_visibility", "updated_at"])
    _jwt(api, jean)
    r = api.get(f"/api/v1/users/{marie.id}")
    assert r.status_code == 200
    assert r.data["data"]["user"]["avatar_url"] == url


@pytest.mark.django_db
def test_colleague_pending_and_inactive_404(api, jean, user_role):
    pending = User.objects.create_user(
        email="pending@yas.tg",
        password=PASSWORD,
        username="pending.user",
        role=user_role,
        pending_approval=True,
        is_active=False,
    )
    inactive = close_gates(
        User.objects.create_user(
            email="off@yas.tg",
            password=PASSWORD,
            username="user.off",
            role=user_role,
            is_active=False,
        )
    )
    _jwt(api, jean)
    r1 = api.get(f"/api/v1/users/{pending.id}")
    assert r1.status_code == 404
    assert r1.data["code"] == "NOT_FOUND"
    r2 = api.get(f"/api/v1/users/{inactive.id}")
    assert r2.status_code == 404
    assert r2.data["code"] == "NOT_FOUND"
    missing = api.get(f"/api/v1/users/{uuid4()}")
    assert missing.status_code == 404


@pytest.mark.django_db
def test_users_self_use_me(api, jean):
    _jwt(api, jean)
    r = api.get(f"/api/v1/users/{jean.id}")
    assert r.status_code == 400
    assert r.data["code"] == "USE_ME"


@pytest.mark.django_db
def test_avatar_jpeg_skipped(api, jean, media_root):
    _jwt(api, jean)
    r = api.post("/api/v1/me/avatar", {"file": _jpeg()}, format="multipart")
    assert r.status_code == 200
    jean.refresh_from_db()
    assert jean.avatar_id is not None
    assert str(jean.avatar_id) == r.data["data"]["avatar_id"]
    media = MediaFile.objects.get(pk=jean.avatar_id)
    assert media.scan_status == MediaFile.ScanStatus.SKIPPED
    assert media.media_type == MediaFile.MediaType.IMAGE
    assert MediaFile.objects.filter(owner=jean).count() == 1
    assert AuditLog.objects.filter(action="AVATAR_SET", entity_id=jean.id).exists()
    blob = api.get(r.data["data"]["avatar_url"])
    assert blob.status_code == 200


@pytest.mark.django_db
def test_avatar_too_large(api, jean, media_root):
    _jwt(api, jean)
    r = api.post("/api/v1/me/avatar", {"file": _jpeg(size=3 * 1024 * 1024)}, format="multipart")
    assert r.status_code == 400
    assert r.data["code"] == "AVATAR_TOO_LARGE"
    jean.refresh_from_db()
    assert jean.avatar_id is None


@pytest.mark.django_db
def test_avatar_invalid_plain(api, jean, media_root):
    _jwt(api, jean)
    r = api.post(
        "/api/v1/me/avatar",
        {"file": _jpeg(size=12, content_type="text/plain", name="x.txt")},
        format="multipart",
    )
    assert r.status_code == 400
    assert r.data["code"] == "INVALID_MEDIA"


@pytest.mark.django_db
def test_avatar_delete_keeps_media_row(api, jean, media_root):
    _jwt(api, jean)
    up = api.post("/api/v1/me/avatar", {"file": _jpeg()}, format="multipart")
    assert up.status_code == 200
    media_id = up.data["data"]["avatar_id"]
    r = api.delete("/api/v1/me/avatar")
    assert r.status_code == 200
    assert r.data["data"]["ok"] is True
    jean.refresh_from_db()
    assert jean.avatar_id is None
    assert MediaFile.objects.filter(pk=media_id).exists()
    me = api.get("/api/v1/me/")
    assert me.data["data"]["user"]["avatar_url"] is None
    assert AuditLog.objects.filter(action="AVATAR_CLEAR", entity_id=jean.id).exists()


@pytest.mark.django_db
def test_patch_name_updates_display_name(api, jean):
    _jwt(api, jean)
    r = api.patch("/api/v1/me/", {"first_name": "Jean-Marc"}, format="json")
    assert r.status_code == 200
    assert r.data["data"]["user"]["display_name"] == "Jean-Marc Dupont"
    assert "role" not in r.data["data"]["user"]
    assert AuditLog.objects.filter(action="PROFILE_PATCH", entity_id=jean.id).exists()


@pytest.mark.django_db
def test_patch_matricule_forbidden(api, jean):
    _jwt(api, jean)
    r = api.patch("/api/v1/me/", {"matricule": "TG2026015"}, format="json")
    assert r.status_code == 400
    assert r.data["code"] == "FIELD_FORBIDDEN"


@pytest.mark.django_db
def test_patch_username_taken(api, jean, marie):
    _jwt(api, jean)
    r = api.patch("/api/v1/me/", {"username": "marie.koevi"}, format="json")
    assert r.status_code == 409
    assert r.data["code"] == "USERNAME_TAKEN"


@pytest.mark.django_db
def test_patch_job_title_forbidden(api, jean):
    _jwt(api, jean)
    r = api.patch("/api/v1/me/", {"job_title": "Ingénieur"}, format="json")
    assert r.status_code == 400
    assert r.data["code"] == "FIELD_FORBIDDEN"


@pytest.mark.django_db
def test_patch_email_forbidden(api, jean):
    _jwt(api, jean)
    r = api.patch("/api/v1/me/", {"email": "autre@yas.tg"}, format="json")
    assert r.status_code == 400
    assert r.data["code"] == "FIELD_FORBIDDEN"


@pytest.mark.django_db
def test_patch_phone_e164_and_null(api, jean):
    _jwt(api, jean)
    ok = api.patch("/api/v1/me/", {"phone": "22890123456"}, format="json")
    assert ok.status_code == 400
    r = api.patch("/api/v1/me/", {"phone": "+22890123456"}, format="json")
    assert r.status_code == 200
    assert r.data["data"]["user"]["phone"] == "+22890123456"
    cleared = api.patch("/api/v1/me/", {"phone": None}, format="json")
    assert cleared.status_code == 200
    assert cleared.data["data"]["user"]["phone"] is None


@pytest.mark.django_db
def test_colleague_has_role_me_does_not(api, jean, marie):
    _jwt(api, jean)
    other = api.get(f"/api/v1/users/{marie.id}")
    assert other.status_code == 200
    role = other.data["data"]["user"]["role"]
    assert role["code"] == "USER"
    assert role["name"] == "Utilisateur"
    me = api.get("/api/v1/me/")
    assert "role" not in me.data["data"]["user"]


@pytest.mark.django_db
def test_org_path_and_manager(api, jean, marie):
    region = Region.objects.create(code="MARITIME", name="Maritime")
    t_dir = SegmentType.objects.create(code="DIRECTION", name="Direction", level=0)
    t_svc = SegmentType.objects.create(code="SERVICE", name="Service", level=2)
    direction = Segment.objects.create(
        code="DSI",
        name="DSI",
        segment_type=t_dir,
        is_active=True,
        responsable=marie,
    )
    noc = Segment.objects.create(
        code="NOC-LOME",
        name="NOC Lomé",
        segment_type=t_svc,
        parent_segment=direction,
        is_active=True,
    )
    jean.segment_id = noc.id
    jean.region = region
    jean.save(update_fields=["segment_id", "region", "updated_at"])
    _jwt(api, jean)
    r = api.get("/api/v1/me/")
    assert r.status_code == 200
    user = r.data["data"]["user"]
    org = user["org"]
    assert org["segment"]["code"] == "NOC-LOME"
    assert org["department"]["name"] == "NOC Lomé"
    assert org["direction"]["name"] == "DSI"
    assert org["path"][0]["name"] == "NOC Lomé"
    assert org["path"][0]["type"] == "SERVICE"
    assert org["path"][1]["name"] == "DSI"
    assert org["manager"]["username"] == "marie.koevi"
    assert user["region"]["code"] == "MARITIME"


@pytest.mark.django_db
def test_ldap_patch_phone(api, user_role):
    ldap_user = close_gates(
        User.objects.create_user(
            email="ldap.user@yas.tg",
            password=PASSWORD,
            username="ldap.user",
            role=user_role,
            first_name="Ldap",
            last_name="User",
            ldap_dn="cn=ldap.user,ou=users,dc=yas,dc=tg",
        )
    )
    _jwt(api, ldap_user)
    r = api.patch("/api/v1/me/", {"phone": "+22890111111"}, format="json")
    assert r.status_code == 200
    assert r.data["data"]["user"]["phone"] == "+22890111111"


@pytest.mark.django_db
def test_jean_without_read_other_403(api, jean, marie):
    RolePermission.objects.filter(
        role=jean.role, permission__code="iam.profile.read_other"
    ).delete()
    invalidate_role_cache(jean.role_id)
    _jwt(api, jean)
    r = api.get(f"/api/v1/users/{marie.id}")
    assert r.status_code == 403
    assert r.data["code"] == "FORBIDDEN"
    assert r.data["permission"] == "iam.profile.read_other"


@pytest.mark.django_db
def test_users_without_jwt_401(api, marie):
    r = api.get(f"/api/v1/users/{marie.id}")
    assert r.status_code == 401


@pytest.mark.django_db
def test_schema_has_prof_a_paths(api, db):
    assert api.get("/health").status_code == 200
    schema = api.get("/api/schema/")
    assert schema.status_code == 200
    text = schema.content.decode()
    assert "/api/v1/users/{id}" in text or "/api/v1/users/{pk}" in text
    assert "/api/v1/me/avatar" in text
    assert api.get("/api/docs/").status_code == 200


@pytest.mark.django_db
def test_colleague_status_nobody_is_null(api, jean, marie):
    marie.status = User.PresenceStatus.ONLINE
    marie.last_login = timezone.now()
    marie.save(update_fields=["status", "last_login", "updated_at"])
    priv = marie.privacy
    priv.online_status_visibility = Visibility.NOBODY
    priv.last_seen_visibility = Visibility.NOBODY
    priv.save(
        update_fields=[
            "online_status_visibility",
            "last_seen_visibility",
            "updated_at",
        ]
    )
    _jwt(api, jean)
    r = api.get(f"/api/v1/users/{marie.id}")
    assert r.status_code == 200
    user = r.data["data"]["user"]
    assert user["status"] is None
    assert user["last_seen"] is None
    assert user["display_name"] == "Marie Koevi"
