"""MESSAGERIE-F : blocage utilisateur, signalement, modération admin."""

import base64
from datetime import timedelta

import pytest
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APIClient

from apps.iam.helpers.compliance import close_gates
from apps.iam.helpers.mfa import login_until_jwt
from apps.iam.models import Role, User
from apps.messaging.models import BlockedUser, ReportedMessage

PASSWORD = "Secret123!"
UA = "Mozilla/5.0 pytest"


@pytest.fixture
def api():
    cache.clear()
    client = APIClient()
    client.defaults["HTTP_USER_AGENT"] = UA
    return client


@pytest.fixture
def user_role(db):
    return Role.objects.create(code="USER", name="Utilisateur", is_system=True, level=0)


def _make_user(user_role, email, username, first_name, last_name):
    return close_gates(
        User.objects.create_user(
            email=email, password=PASSWORD, username=username,
            role=user_role, first_name=first_name, last_name=last_name,
        )
    )


@pytest.fixture
def jean(user_role):
    return _make_user(user_role, "jean.dupont@yas.tg", "jean.dupont", "Jean", "Dupont")


@pytest.fixture
def marie(user_role):
    return _make_user(user_role, "marie.koevi@yas.tg", "marie.koevi", "Marie", "Koevi")


@pytest.fixture
def admin_role(db):
    return Role.objects.create(code="ADMIN", name="Administrateur", is_system=True, level=100)


@pytest.fixture
def admin(admin_role):
    return _make_user(admin_role, "admin.msgf@yas.tg", "admin.msgf", "Admin", "YAS")


def _jwt(api, user, *, password=PASSWORD, device_uuid="web-1"):
    device = {"device_uuid": device_uuid, "platform": "WEB"}
    r = login_until_jwt(api, email=user.email, password=password, device=device)
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {r.data['data']['access_token']}")
    return r


def _create_group(api, title, member_ids):
    return api.post(
        "/api/v1/conversations",
        {"type": "GROUP", "title": title, "member_ids": [str(i) for i in member_ids]},
        format="json",
    ).data["data"]["id"]


def _send(api, conv_id, text=b"hi"):
    body = {"type": "TEXT", "encrypted_content": base64.b64encode(text).decode()}
    return api.post(f"/api/v1/conversations/{conv_id}/messages", body, format="json").data["data"]


# --- MSG-89/90/91 : blocage ----------------------------------------------------------


@pytest.mark.django_db
def test_block_self_400(api, jean):
    _jwt(api, jean)
    r = api.post("/api/v1/me/blocked-users", {"user_id": str(jean.id)}, format="json")
    assert r.status_code == 400


@pytest.mark.django_db
def test_block_twice_409(api, jean, marie):
    _jwt(api, jean)
    r1 = api.post("/api/v1/me/blocked-users", {"user_id": str(marie.id)}, format="json")
    assert r1.status_code == 201
    r2 = api.post("/api/v1/me/blocked-users", {"user_id": str(marie.id)}, format="json")
    assert r2.status_code == 409
    assert r2.data["code"] == "ALREADY_BLOCKED"


@pytest.mark.django_db
def test_get_blocked_users(api, jean, marie):
    _jwt(api, jean)
    api.post(
        "/api/v1/me/blocked-users", {"user_id": str(marie.id), "reason": "spam"}, format="json"
    )
    r = api.get("/api/v1/me/blocked-users")
    assert r.status_code == 200
    assert r.data["data"]["results"][0]["user_id"] == str(marie.id)


@pytest.mark.django_db
def test_unblock_allows_new_private(api, jean, marie):
    _jwt(api, jean)
    api.post("/api/v1/me/blocked-users", {"user_id": str(marie.id)}, format="json")
    blocked_attempt = api.post(
        "/api/v1/conversations", {"type": "PRIVATE", "participant_id": str(marie.id)}, format="json"
    )
    assert blocked_attempt.status_code == 403

    r = api.delete(f"/api/v1/me/blocked-users/{marie.id}")
    assert r.status_code == 200
    assert not BlockedUser.objects.filter(blocker=jean, blocked=marie).exists()


# --- MSG-93/94/98 : signalement --------------------------------------------------------


@pytest.mark.django_db
def test_report_empty_reason_400(api, jean, marie):
    _jwt(api, jean)
    conv_id = _create_group(api, "Equipe", [marie.id])
    message = _send(api, conv_id)
    r = api.post(f"/api/v1/messages/{message['id']}/reports", {"reason": ""}, format="json")
    assert r.status_code == 400


@pytest.mark.django_db
def test_report_rate_limited(api, jean, marie):
    _jwt(api, jean)
    conv_id = _create_group(api, "Equipe", [marie.id])
    message = _send(api, conv_id)
    for _ in range(10):
        ReportedMessage.objects.create(message_id=message["id"], reason="x", reported_by=jean)
    r = api.post(f"/api/v1/messages/{message['id']}/reports", {"reason": "abus"}, format="json")
    assert r.status_code == 429
    assert r.data["code"] == "REPORT_RATE_LIMITED"


@pytest.mark.django_db
def test_report_old_reports_dont_count(api, jean, marie):
    _jwt(api, jean)
    conv_id = _create_group(api, "Equipe", [marie.id])
    message = _send(api, conv_id)
    for _ in range(10):
        ReportedMessage.objects.create(message_id=message["id"], reason="x", reported_by=jean)
    old = timezone.now() - timedelta(hours=25)
    ReportedMessage.objects.filter(reported_by=jean).update(created_at=old)
    r = api.post(f"/api/v1/messages/{message['id']}/reports", {"reason": "abus"}, format="json")
    assert r.status_code == 201


# --- MSG-95/96 : modération admin --------------------------------------------------------


@pytest.mark.django_db
def test_admin_reported_messages_without_perm_403(api, jean, marie):
    _jwt(api, jean)
    conv_id = _create_group(api, "Equipe", [marie.id])
    message = _send(api, conv_id)
    api.post(f"/api/v1/messages/{message['id']}/reports", {"reason": "abus"}, format="json")
    r = api.get("/api/v1/admin/reported-messages")
    assert r.status_code == 403
    assert r.data["code"] == "FORBIDDEN"


@pytest.mark.django_db
def test_admin_reported_messages_list_and_review(api, jean, marie, admin):
    _jwt(api, jean)
    conv_id = _create_group(api, "Equipe", [marie.id])
    message = _send(api, conv_id)
    report = api.post(
        f"/api/v1/messages/{message['id']}/reports", {"reason": "abus"}, format="json"
    ).data["data"]

    _jwt(api, admin)
    listed = api.get("/api/v1/admin/reported-messages?status=PENDING")
    assert listed.status_code == 200
    assert any(row["id"] == report["id"] for row in listed.data["data"]["results"])

    r = api.patch(
        f"/api/v1/admin/reported-messages/{report['id']}",
        {"status": "REVIEWED"},
        format="json",
    )
    assert r.status_code == 200
    updated = ReportedMessage.objects.get(pk=report["id"])
    assert updated.status == "REVIEWED"
    assert updated.reviewed_by_id == admin.id
    assert updated.reviewed_at is not None


@pytest.mark.django_db
def test_schema_has_blocked_users_path(api, db):
    schema = api.get("/api/schema/")
    assert schema.status_code == 200
    assert "blocked-users" in schema.content.decode()
