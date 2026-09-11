"""ADMIN-A : liste/fiche, create RH, disable/enable, reset MDP, kick, audit, régions."""

from uuid import uuid4

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.annuaire.models import Segment, SegmentType
from apps.iam.helpers.compliance import close_gates
from apps.iam.helpers.mfa import login_until_jwt
from apps.iam.models import (
    AuditLog,
    Permission,
    Region,
    Role,
    RolePermission,
    Session,
    User,
)
from apps.iam.services.rbac_service import invalidate_role_cache

DEVICE = {"device_uuid": "test-web-1", "platform": "WEB"}
UA = "Mozilla/5.0 pytest"
PASSWORD = "Secret123!"
ADMIN_PASSWORD = "Admin123!"
CREATE_PASSWORD = "SecretApp456!"
NEW_PASSWORD = "SecretApp789!"


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
def admin_role(db):
    return Role.objects.create(code="ADMIN", name="Administrateur", is_system=True, level=100)


@pytest.fixture
def region(db):
    return Region.objects.create(code="MARITIME", name="Maritime")


@pytest.fixture
def segment(db):
    st = SegmentType.objects.create(code="DIRECTION", name="Direction", level=0)
    return Segment.objects.create(code="YAS", name="YAS Togo", segment_type=st, is_active=True)


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


@pytest.fixture
def admin_ok(admin_role):
    return close_gates(
        User.objects.create_user(
            email="admin@yas.tg",
            password=ADMIN_PASSWORD,
            username="admin.yas",
            role=admin_role,
            first_name="Admin",
            last_name="YAS",
        )
    )


def _jwt(api, user, *, password=PASSWORD, device=DEVICE):
    r = login_until_jwt(api, email=user.email, password=password, device=device)
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {r.data['data']['access_token']}")
    return r


def _admin(api, admin_ok):
    return _jwt(api, admin_ok, password=ADMIN_PASSWORD)


def _create_body(region, segment, **extra):
    body = {
        "email": "marie.koevi@yas.tg",
        "password": CREATE_PASSWORD,
        "first_name": "Marie",
        "last_name": "Koevi",
        "phone": "+22890111111",
        "job_title": "RH",
        "region_id": str(region.id),
        "segment_id": str(segment.id),
        "matricule": "TG2026100",
    }
    body.update(extra)
    return body


@pytest.mark.django_db
def test_list_jean_forbidden(api, user_ok, admin_ok):
    _jwt(api, user_ok)
    r = api.get("/api/v1/admin/users")
    assert r.status_code == 403
    assert r.data["code"] == "FORBIDDEN"
    assert r.data["permission"] == "iam.user.read"


@pytest.mark.django_db
def test_list_pending_file(api, user_ok, admin_ok):
    pending = User.objects.create_user(
        email="pending@yas.tg",
        password=PASSWORD,
        username="pending.user",
        role=user_ok.role,
        pending_approval=True,
        is_active=False,
    )
    _admin(api, admin_ok)
    r = api.get("/api/v1/admin/users?pending=true")
    assert r.status_code == 200
    assert r.data["data"]["count"] == 1
    row = r.data["data"]["results"][0]
    assert row["email"] == pending.email
    assert row["display_name"]
    assert "role" in row
    assert "password" not in row
    assert "ldap_dn" not in row


@pytest.mark.django_db
def test_detail_no_secrets(api, user_ok, admin_ok, region, segment):
    user_ok.region = region
    user_ok.segment_id = segment.id
    user_ok.save(update_fields=["region", "segment_id", "updated_at"])
    _admin(api, admin_ok)
    r = api.get(f"/api/v1/admin/users/{user_ok.id}")
    assert r.status_code == 200
    data = r.data["data"]
    assert data["email"] == user_ok.email
    assert data["role"]["code"] == "USER"
    assert data["region"]["code"] == "MARITIME"
    assert data["segment_id"] == str(segment.id)
    assert "password" not in data
    assert "ldap_dn" not in data
    blob = str(data)
    assert "argon" not in blob.lower()
    assert "password_hash" not in blob


@pytest.mark.django_db
def test_detail_unknown_404(api, admin_ok):
    _admin(api, admin_ok)
    r = api.get(f"/api/v1/admin/users/{uuid4()}")
    assert r.status_code == 404
    assert r.data["code"] == "NOT_FOUND"


@pytest.mark.django_db
def test_create_ok_then_login_enroll(api, user_ok, admin_ok, region, segment):
    _admin(api, admin_ok)
    r = api.post("/api/v1/admin/users", _create_body(region, segment), format="json")
    assert r.status_code == 201
    data = r.data["data"]
    assert data["role"]["code"] == "USER"
    assert data["is_active"] is True
    assert data["pending_approval"] is False
    assert data["ldap_bound"] is False
    assert data["username"] == "mkoevi"
    assert "password" not in data
    user = User.objects.get(email="marie.koevi@yas.tg")
    assert user.ldap_dn is None
    assert AuditLog.objects.filter(action="USER_CREATE", entity_id=user.id).exists()
    api.credentials()
    login = api.post(
        "/api/v1/auth/login",
        {"email": "marie.koevi@yas.tg", "password": CREATE_PASSWORD, "device": DEVICE},
        format="json",
    )
    assert login.status_code == 200
    assert login.data["data"]["mfa_required"] is True
    assert login.data["data"]["enroll"] is True
    assert "access_token" not in login.data["data"]


@pytest.mark.django_db
def test_create_role_code_forbidden(api, admin_ok, region, segment):
    _admin(api, admin_ok)
    r = api.post(
        "/api/v1/admin/users",
        _create_body(region, segment, role_code="ADMIN"),
        format="json",
    )
    assert r.status_code == 400
    assert r.data["code"] == "FIELD_FORBIDDEN"


@pytest.mark.django_db
def test_create_email_taken(api, user_ok, admin_ok, region, segment):
    _admin(api, admin_ok)
    r = api.post(
        "/api/v1/admin/users",
        _create_body(region, segment, email=user_ok.email),
        format="json",
    )
    assert r.status_code == 409
    assert r.data["code"] == "EMAIL_TAKEN"


@pytest.mark.django_db
def test_disable_hors_ad(api, user_ok, admin_ok):
    _jwt(api, user_ok)
    assert Session.objects.filter(user=user_ok, is_active=True).exists()
    api.credentials()
    _admin(api, admin_ok)
    r = api.post(
        f"/api/v1/admin/users/{user_ok.id}/disable",
        {"reason": "départ"},
        format="json",
    )
    assert r.status_code == 200
    user_ok.refresh_from_db()
    assert user_ok.is_active is False
    assert Session.objects.filter(user=user_ok, is_active=True).count() == 0
    api.credentials()
    login = api.post(
        "/api/v1/auth/login",
        {"email": user_ok.email, "password": PASSWORD, "device": DEVICE},
        format="json",
    )
    assert login.status_code == 403
    assert login.data["code"] == "ACCOUNT_DISABLED"


@pytest.mark.django_db
def test_disable_last_admin(api, user_ok, admin_ok):
    perm = Permission.objects.get(code="iam.user.disable")
    RolePermission.objects.get_or_create(role=user_ok.role, permission=perm)
    invalidate_role_cache(user_ok.role_id)
    _jwt(api, user_ok)
    r = api.post(f"/api/v1/admin/users/{admin_ok.id}/disable")
    assert r.status_code == 409
    assert r.data["code"] == "LAST_ADMIN"


@pytest.mark.django_db
def test_disable_ldap_managed(api, user_ok, admin_ok):
    user_ok.ldap_dn = "CN=Jean,DC=yas,DC=tg"
    user_ok.save(update_fields=["ldap_dn", "updated_at"])
    _admin(api, admin_ok)
    r = api.post(f"/api/v1/admin/users/{user_ok.id}/disable")
    assert r.status_code == 400
    assert r.data["code"] == "LDAP_MANAGED"


@pytest.mark.django_db
def test_disable_self(api, admin_ok):
    _admin(api, admin_ok)
    r = api.post(f"/api/v1/admin/users/{admin_ok.id}/disable")
    assert r.status_code == 400
    assert r.data["code"] == "CANNOT_ACT_ON_SELF"


@pytest.mark.django_db
def test_enable_pending(api, user_ok, admin_ok):
    pending = User.objects.create_user(
        email="pending@yas.tg",
        password=PASSWORD,
        username="pending.user",
        role=user_ok.role,
        pending_approval=True,
        is_active=False,
    )
    _admin(api, admin_ok)
    r = api.post(f"/api/v1/admin/users/{pending.id}/enable")
    assert r.status_code == 400
    assert r.data["code"] == "STILL_PENDING"


@pytest.mark.django_db
def test_enable_after_disable_keeps_lock(api, user_ok, admin_ok):
    user_ok.is_locked = True
    user_ok.save(update_fields=["is_locked", "updated_at"])
    _admin(api, admin_ok)
    off = api.post(f"/api/v1/admin/users/{user_ok.id}/disable")
    assert off.status_code == 200
    on = api.post(f"/api/v1/admin/users/{user_ok.id}/enable")
    assert on.status_code == 200
    user_ok.refresh_from_db()
    assert user_ok.is_active is True
    assert user_ok.is_locked is True
    user_ok.is_locked = False
    user_ok.save(update_fields=["is_locked", "updated_at"])
    api.credentials()
    ok = login_until_jwt(api, email=user_ok.email, password=PASSWORD, device=DEVICE)
    assert ok.status_code == 200
    assert "access_token" in ok.data["data"]


@pytest.mark.django_db
def test_reset_password(api, user_ok, admin_ok):
    first = _jwt(api, user_ok)
    refresh = first.data["data"]["refresh_token"]
    api.credentials()
    _admin(api, admin_ok)
    r = api.post(
        f"/api/v1/admin/users/{user_ok.id}/password",
        {"new_password": NEW_PASSWORD},
        format="json",
    )
    assert r.status_code == 200
    assert r.data["data"] == {"ok": True}
    assert "password" not in str(r.data).lower() or r.data["data"].get("ok") is True
    assert NEW_PASSWORD not in str(r.data)
    user_ok.refresh_from_db()
    assert user_ok.check_password(NEW_PASSWORD)
    api.credentials()
    stale = api.post("/api/v1/auth/refresh", {"refresh_token": refresh}, format="json")
    assert stale.status_code == 401
    ok = login_until_jwt(api, email=user_ok.email, password=NEW_PASSWORD, device=DEVICE)
    assert ok.status_code == 200


@pytest.mark.django_db
def test_reset_password_policy(api, user_ok, admin_ok):
    _admin(api, admin_ok)
    r = api.post(
        f"/api/v1/admin/users/{user_ok.id}/password",
        {"new_password": "short"},
        format="json",
    )
    assert r.status_code == 400
    assert r.data["code"] == "WEAK_PASSWORD"


@pytest.mark.django_db
def test_reset_password_ldap_ok(api, user_ok, admin_ok):
    user_ok.ldap_dn = "CN=Jean,DC=yas,DC=tg"
    user_ok.save(update_fields=["ldap_dn", "updated_at"])
    _admin(api, admin_ok)
    r = api.post(
        f"/api/v1/admin/users/{user_ok.id}/password",
        {"new_password": NEW_PASSWORD},
        format="json",
    )
    assert r.status_code == 200
    user_ok.refresh_from_db()
    assert user_ok.ldap_dn == "CN=Jean,DC=yas,DC=tg"
    assert user_ok.check_password(NEW_PASSWORD)


@pytest.mark.django_db
def test_revoke_all(api, user_ok, admin_ok):
    first = _jwt(api, user_ok)
    refresh = first.data["data"]["refresh_token"]
    api.credentials()
    _admin(api, admin_ok)
    r = api.post(f"/api/v1/admin/users/{user_ok.id}/sessions/revoke-all")
    assert r.status_code == 200
    assert r.data["data"]["revoked"] >= 1
    user_ok.refresh_from_db()
    assert user_ok.is_active is True
    api.credentials()
    stale = api.post("/api/v1/auth/refresh", {"refresh_token": refresh}, format="json")
    assert stale.status_code == 401


@pytest.mark.django_db
def test_revoke_all_self(api, admin_ok):
    _admin(api, admin_ok)
    r = api.post(f"/api/v1/admin/users/{admin_ok.id}/sessions/revoke-all")
    assert r.status_code == 400
    assert r.data["code"] == "CANNOT_ACT_ON_SELF"


@pytest.mark.django_db
def test_audit_after_disable(api, user_ok, admin_ok):
    _admin(api, admin_ok)
    api.post(f"/api/v1/admin/users/{user_ok.id}/disable", {"reason": "audit"}, format="json")
    r = api.get("/api/v1/admin/audit-logs?action=USER_DISABLE")
    assert r.status_code == 200
    assert r.data["data"]["count"] >= 1
    row = r.data["data"]["results"][0]
    assert row["action"] == "USER_DISABLE"
    assert row["entity_id"] == str(user_ok.id)
    assert row["metadata"]["reason"] == "audit"


@pytest.mark.django_db
def test_region_create_and_delete(api, admin_ok):
    _admin(api, admin_ok)
    r = api.post("/api/v1/admin/regions", {"code": "GOLFE", "name": "Golfe"}, format="json")
    assert r.status_code == 201
    region_id = r.data["data"]["id"]
    gone = api.delete(f"/api/v1/admin/regions/{region_id}")
    assert gone.status_code == 204
    assert not Region.objects.filter(pk=region_id).exists()


@pytest.mark.django_db
def test_region_delete_in_use(api, user_ok, admin_ok, region):
    user_ok.region = region
    user_ok.save(update_fields=["region", "updated_at"])
    _admin(api, admin_ok)
    r = api.delete(f"/api/v1/admin/regions/{region.id}")
    assert r.status_code == 409
    assert r.data["code"] == "REGION_IN_USE"
    assert r.data["users_count"] >= 1


@pytest.mark.django_db
def test_without_jwt(api, db):
    r = api.get("/api/v1/admin/users")
    assert r.status_code == 401


@pytest.mark.django_db
def test_admin_without_tos_can_list(api, admin_role):
    admin = User.objects.create_user(
        email="admin.fresh@yas.tg",
        password=ADMIN_PASSWORD,
        username="admin.fresh",
        role=admin_role,
    )
    _jwt(api, admin, password=ADMIN_PASSWORD)
    r = api.get("/api/v1/admin/users")
    assert r.status_code == 200
    me_devices = api.get("/api/v1/me/devices")
    assert me_devices.status_code == 403
    assert me_devices.data["code"] == "TOS_REQUIRED"


@pytest.mark.django_db
def test_schema_has_admin_a_paths(api, db):
    assert api.get("/health").status_code == 200
    schema = api.get("/api/schema/")
    assert schema.status_code == 200
    text = schema.content.decode()
    assert "/api/v1/admin/users/{id}" in text or "/api/v1/admin/users/{pk}" in text
    assert "/api/v1/admin/regions" in text
    assert api.get("/api/docs/").status_code == 200
