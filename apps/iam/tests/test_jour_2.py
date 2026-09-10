"""Jour 2 : /admin/ (rôle ADMIN) + schéma Swagger AUTH-A."""

import pytest
from django.test import Client
from rest_framework.test import APIClient

from apps.iam.helpers.compliance import close_gates
from apps.iam.models import Role, User

ADMIN_PASSWORD = "Admin123!"
USER_PASSWORD = "Secret123!"


@pytest.fixture
def api():
    return APIClient()


@pytest.fixture
def browser():
    """Client Django (cookie + CSRF) pour /admin/, pas l’API JWT."""
    return Client()


@pytest.fixture
def roles(db):
    user_role = Role.objects.create(code="USER", name="Utilisateur", is_system=True, level=0)
    admin_role = Role.objects.create(code="ADMIN", name="Administrateur", is_system=True, level=100)
    return user_role, admin_role


@pytest.fixture
def user_ok(roles):
    user_role, _ = roles
    return close_gates(
        User.objects.create_user(
            email="jean.dupont@yas.tg",
            password=USER_PASSWORD,
            username="jean.dupont",
            role=user_role,
        )
    )


@pytest.fixture
def admin_ok(roles):
    _, admin_role = roles
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


@pytest.mark.django_db
def test_admin_property_only_admin_role(user_ok, admin_ok):
    """Pas de colonne is_staff : la propriété suit role.code."""
    assert user_ok.is_staff is False
    assert admin_ok.is_staff is True
    assert admin_ok.has_module_perms("iam") is True


@pytest.mark.django_db
def test_admin_login_ok(browser, admin_ok):
    ok = browser.login(email=admin_ok.email, password=ADMIN_PASSWORD)
    assert ok is True
    r = browser.get("/admin/")
    assert r.status_code == 200
    assert b"users" in r.content.lower() or b"Users" in r.content or b"IAM" in r.content


@pytest.mark.django_db
def test_admin_user_role_rejected(browser, user_ok):
    """jean.dupont (USER) : session Django possible mais /admin/ refuse (pas staff)."""
    browser.login(email=user_ok.email, password=USER_PASSWORD)
    r = browser.get("/admin/")
    assert r.status_code == 302
    assert "/admin/login" in r["Location"]


@pytest.mark.django_db
def test_swagger_docs_public(api):
    r = api.get("/api/docs/")
    assert r.status_code == 200


@pytest.mark.django_db
def test_openapi_schema_has_auth_routes(api):
    r = api.get("/api/schema/")
    assert r.status_code == 200
    body = r.content.decode()
    assert "/api/v1/auth/login" in body
    assert "/api/v1/auth/refresh" in body
    assert "bearerAuth" in body
    assert "health" in body.lower() or "/health" in body
