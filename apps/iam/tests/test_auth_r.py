"""AUTH-R : seed 58, HasPermission fail-closed, CRUD rôles / matrice / LAST_ADMIN."""

import re
from unittest.mock import patch

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient, APIRequestFactory

from apps.iam.exceptions import AuthAPIError
from apps.iam.helpers.compliance import close_gates
from apps.iam.helpers.mfa import login_until_jwt
from apps.iam.middlewares.permissions import HasPermission
from apps.iam.models import AuditLog, Device, Permission, Role, RolePermission, User
from apps.iam.services.rbac_catalog import (
    ALL_SYSTEM_CODES,
    CODE_RE,
    SELF_PERMISSION_CODES,
)
from apps.iam.services.rbac_service import invalidate_role_cache

DEVICE = {"device_uuid": "test-web-1", "platform": "WEB"}
UA = "Mozilla/5.0 pytest"
PASSWORD = "Secret123!"
ADMIN_PASSWORD = "Admin123!"
CODE_RX = re.compile(CODE_RE)


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


@pytest.mark.django_db
def test_seed_codes_regex(user_ok, admin_ok):
    assert Role.objects.filter(code="USER", is_system=True).exists()
    assert Role.objects.filter(code="ADMIN", is_system=True).exists()
    qs = Permission.objects.filter(is_system=True)
    assert qs.count() == 58
    for code in qs.values_list("code", flat=True):
        assert CODE_RX.fullmatch(code), code
    assert Permission.objects.filter(code__in=SELF_PERMISSION_CODES).count() == 27
    assert set(ALL_SYSTEM_CODES) == set(qs.values_list("code", flat=True))


@pytest.mark.django_db
def test_jean_get_me_200(api, user_ok):
    _jwt(api, user_ok)
    r = api.get("/api/v1/me/")
    assert r.status_code == 200
    assert r.data["data"]["user"]["email"] == user_ok.email


@pytest.mark.django_db
def test_jean_approve_forbidden(api, user_ok, admin_ok):
    pending = close_gates(
        User.objects.create_user(
            email="pending@yas.tg",
            password=PASSWORD,
            username="pending.user",
            role=user_ok.role,
            pending_approval=True,
            is_active=False,
        )
    )
    _jwt(api, user_ok)
    r = api.post(f"/api/v1/admin/users/{pending.id}/approve")
    assert r.status_code == 403
    assert r.data["code"] == "FORBIDDEN"
    assert r.data["permission"] == "iam.user.approve"


@pytest.mark.django_db
def test_remove_profile_read_forbids_me(api, user_ok, admin_ok):
    RolePermission.objects.filter(role=user_ok.role, permission__code="iam.profile.read").delete()
    invalidate_role_cache(user_ok.role_id)
    _jwt(api, user_ok)
    r = api.get("/api/v1/me/")
    assert r.status_code == 403
    assert r.data["code"] == "FORBIDDEN"
    assert r.data["permission"] == "iam.profile.read"


@pytest.mark.django_db
def test_admin_approve_200(api, user_ok, admin_ok):
    pending = User.objects.create_user(
        email="pending@yas.tg",
        password=PASSWORD,
        username="pending.user",
        role=user_ok.role,
        pending_approval=True,
        is_active=False,
    )
    _admin(api, admin_ok)
    r = api.post(f"/api/v1/admin/users/{pending.id}/approve")
    assert r.status_code == 200
    pending.refresh_from_db()
    assert pending.is_active is True
    assert pending.pending_approval is False


@pytest.mark.django_db
def test_view_without_required_permission(user_ok):
    class Dummy:
        pass

    factory = APIRequestFactory()
    request = factory.get("/x")
    request.user = user_ok
    with pytest.raises(AuthAPIError) as exc:
        HasPermission().has_permission(request, Dummy())
    assert exc.value.code == "FORBIDDEN"
    assert exc.value.extra["permission"] is None


@pytest.mark.django_db
def test_me_without_jwt_401(api, user_ok):
    r = api.get("/api/v1/me/")
    assert r.status_code == 401


@pytest.mark.django_db
def test_roles_list_jean_403(api, user_ok):
    _jwt(api, user_ok)
    r = api.get("/api/v1/admin/roles")
    assert r.status_code == 403
    assert r.data["code"] == "FORBIDDEN"
    assert r.data["permission"] == "iam.role.read"


@pytest.mark.django_db
def test_roles_crud_and_guards(api, user_ok, admin_ok):
    _admin(api, admin_ok)
    listed = api.get("/api/v1/admin/roles")
    assert listed.status_code == 200
    codes = {row["code"] for row in listed.data["data"]["roles"]}
    assert "USER" in codes and "ADMIN" in codes
    admin_id = next(row["id"] for row in listed.data["data"]["roles"] if row["code"] == "ADMIN")
    detail = api.get(f"/api/v1/admin/roles/{admin_id}")
    assert detail.status_code == 200
    assert len(detail.data["data"]["permission_codes"]) == 58

    bad = api.post(
        "/api/v1/admin/roles",
        {"code": "noc_lead", "name": "NOC"},
        format="json",
    )
    assert bad.status_code == 400
    assert bad.data["code"] == "INVALID_ROLE_CODE"

    created = api.post(
        "/api/v1/admin/roles",
        {"code": "NOC_LEAD", "name": "Chef NOC", "description": "lab", "level": 20},
        format="json",
    )
    assert created.status_code == 201
    assert created.data["data"]["is_system"] is False
    assert created.data["data"]["permission_codes"] == []
    noc_id = created.data["data"]["id"]

    again = api.post(
        "/api/v1/admin/roles",
        {"code": "NOC_LEAD", "name": "Chef NOC"},
        format="json",
    )
    assert again.status_code == 409
    assert again.data["code"] == "ROLE_CODE_TAKEN"

    forbidden = api.post(
        "/api/v1/admin/roles",
        {"code": "SEC_ADMIN", "name": "Sec", "is_system": True},
        format="json",
    )
    assert forbidden.status_code == 400
    assert forbidden.data["code"] == "FIELD_FORBIDDEN"

    r_code = api.patch(f"/api/v1/admin/roles/{admin_id}", {"code": "ROOT"}, format="json")
    assert r_code.status_code == 400
    assert r_code.data["code"] == "CODE_IMMUTABLE"
    r_level = api.patch(f"/api/v1/admin/roles/{admin_id}", {"level": 99}, format="json")
    assert r_level.status_code == 400
    assert r_level.data["code"] == "ROLE_SYSTEM_FROZEN"
    r_sys = api.patch(f"/api/v1/admin/roles/{admin_id}", {"is_system": False}, format="json")
    assert r_sys.status_code == 400
    assert r_sys.data["code"] == "FIELD_FORBIDDEN"
    r_name = api.patch(
        f"/api/v1/admin/roles/{admin_id}",
        {"name": "Administrateur plateforme"},
        format="json",
    )
    assert r_name.status_code == 200
    assert r_name.data["data"]["name"] == "Administrateur plateforme"

    patched = api.patch(f"/api/v1/admin/roles/{noc_id}", {"level": 25}, format="json")
    assert patched.status_code == 200
    assert patched.data["data"]["level"] == 25

    user_id = next(row["id"] for row in listed.data["data"]["roles"] if row["code"] == "USER")
    d_user = api.delete(f"/api/v1/admin/roles/{user_id}")
    assert d_user.status_code == 409
    assert d_user.data["code"] == "ROLE_SYSTEM"
    d_admin = api.delete(f"/api/v1/admin/roles/{admin_id}")
    assert d_admin.status_code == 409
    assert d_admin.data["code"] == "ROLE_SYSTEM"

    noc_role = Role.objects.get(pk=noc_id)
    user_ok.role = noc_role
    user_ok.save(update_fields=["role", "updated_at"])
    in_use = api.delete(f"/api/v1/admin/roles/{noc_id}")
    assert in_use.status_code == 409
    assert in_use.data["code"] == "ROLE_IN_USE"
    assert in_use.data["users_count"] == 1
    user_ok.role = Role.objects.get(code="USER")
    user_ok.save(update_fields=["role", "updated_at"])
    gone = api.delete(f"/api/v1/admin/roles/{noc_id}")
    assert gone.status_code == 204
    assert api.get(f"/api/v1/admin/roles/{noc_id}").status_code == 404


@pytest.mark.django_db
def test_permission_create_system_taken(api, admin_ok):
    _admin(api, admin_ok)
    r = api.post(
        "/api/v1/admin/permissions",
        {
            "module": "iam",
            "resource": "user",
            "action": "approve",
            "name": "dup",
        },
        format="json",
    )
    assert r.status_code == 409
    assert r.data["code"] == "PERMISSION_CODE_TAKEN"


@pytest.mark.django_db
def test_matrix_add_remove_put(api, user_ok, admin_ok):
    _admin(api, admin_ok)
    created = api.post(
        "/api/v1/admin/roles",
        {"code": "NOC_LEAD", "name": "Chef NOC"},
        format="json",
    )
    noc_id = created.data["data"]["id"]
    url = f"/api/v1/admin/roles/{noc_id}/permissions"
    added = api.post(url, {"permission_codes": ["iam.user.unlock"]}, format="json")
    assert added.status_code == 200
    assert "iam.user.unlock" in added.data["data"]["permission_codes"]
    audit_add = AuditLog.objects.filter(action="ROLE_PERM_ADD").latest("id")
    assert "iam.user.unlock" in audit_add.new_values["added"]

    again = api.post(url, {"permission_codes": ["iam.user.unlock"]}, format="json")
    assert again.status_code == 200
    audit_dup = AuditLog.objects.filter(action="ROLE_PERM_ADD").latest("id")
    assert audit_dup.new_values["added"] == []

    unknown = api.post(url, {"permission_codes": ["iam.nope.missing"]}, format="json")
    assert unknown.status_code == 404
    assert unknown.data["code"] == "PERMISSION_NOT_FOUND"
    assert unknown.data["permission"] == "iam.nope.missing"
    assert api.get(f"/api/v1/admin/roles/{noc_id}").data["data"]["permission_codes"] == [
        "iam.user.unlock"
    ]

    noc_role = Role.objects.get(pk=noc_id)
    user_ok.role = noc_role
    user_ok.save(update_fields=["role", "updated_at"])
    api.credentials()
    _jwt(api, user_ok)
    unlock = api.post(f"/api/v1/admin/users/{admin_ok.id}/unlock")
    assert unlock.status_code == 200

    _admin(api, admin_ok)
    removed = api.delete(url, {"permission_codes": ["iam.user.unlock"]}, format="json")
    assert removed.status_code == 200
    assert "iam.user.unlock" not in removed.data["data"]["permission_codes"]
    api.credentials()
    _jwt(api, user_ok)
    denied = api.post(f"/api/v1/admin/users/{admin_ok.id}/unlock")
    assert denied.status_code == 403

    _admin(api, admin_ok)
    admin_id = str(Role.objects.get(code="ADMIN").id)
    frozen = api.delete(
        f"/api/v1/admin/roles/{admin_id}/permissions",
        {"permission_codes": ["iam.mfa.reset"]},
        format="json",
    )
    assert frozen.status_code == 409
    assert frozen.data["code"] == "ADMIN_PERMS_FROZEN"

    put = api.put(url, {"permission_codes": ["iam.device.read"]}, format="json")
    assert put.status_code == 200
    assert put.data["data"]["permission_codes"] == ["iam.device.read"]

    put_admin = api.put(
        f"/api/v1/admin/roles/{admin_id}/permissions",
        {"permission_codes": []},
        format="json",
    )
    assert put_admin.status_code == 409
    assert put_admin.data["code"] == "ADMIN_PERMS_FROZEN"


@pytest.mark.django_db
def test_last_admin_and_promote(api, user_ok, admin_ok):
    _admin(api, admin_ok)
    last = api.patch(
        f"/api/v1/admin/users/{admin_ok.id}/role",
        {"role_code": "USER"},
        format="json",
    )
    assert last.status_code == 409
    assert last.data["code"] == "LAST_ADMIN"
    ok = api.patch(
        f"/api/v1/admin/users/{user_ok.id}/role",
        {"role_code": "ADMIN"},
        format="json",
    )
    assert ok.status_code == 200
    user_ok.refresh_from_db()
    assert user_ok.role.code == "ADMIN"
    assert AuditLog.objects.filter(action="USER_ROLE_CHANGE", entity_id=user_ok.id).exists()


@pytest.mark.django_db
def test_password_without_perm(api, user_ok):
    RolePermission.objects.filter(
        role=user_ok.role, permission__code="iam.password.change"
    ).delete()
    invalidate_role_cache(user_ok.role_id)
    _jwt(api, user_ok)
    r = api.post(
        "/api/v1/me/password",
        {"old_password": PASSWORD, "new_password": "Secret456!"},
        format="json",
    )
    assert r.status_code == 403
    assert r.data["permission"] == "iam.password.change"


@pytest.mark.django_db
def test_sessions_user_200(api, user_ok):
    _jwt(api, user_ok)
    r = api.get("/api/v1/me/sessions")
    assert r.status_code == 200
    assert "sessions" in r.data["data"]


@pytest.mark.django_db
def test_admin_compromise_without_manage(api, user_ok, admin_ok):
    _jwt(api, user_ok)
    device = Device.objects.get(user=user_ok)
    RolePermission.objects.filter(
        role=user_ok.role, permission__code="iam.device.manage"
    ).delete()
    invalidate_role_cache(user_ok.role_id)
    r = api.post(f"/api/v1/admin/devices/{device.id}/compromise")
    assert r.status_code == 403
    assert r.data["permission"] == "iam.device.manage"


@pytest.mark.django_db
def test_cache_down_falls_back_sql(api, user_ok):
    _jwt(api, user_ok)
    with (
        patch("apps.iam.services.rbac_service.cache.get", side_effect=ConnectionError),
        patch("apps.iam.services.rbac_service.cache.set", side_effect=ConnectionError),
    ):
        r = api.get("/api/v1/me/")
    assert r.status_code == 200


@pytest.mark.django_db
def test_schema_has_admin_roles(api, db):
    assert api.get("/health").status_code == 200
    schema = api.get("/api/schema/")
    assert schema.status_code == 200
    text = schema.content.decode()
    assert "/api/v1/admin/roles" in text
    assert api.get("/api/docs/").status_code == 200
