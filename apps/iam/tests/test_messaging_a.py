"""MESSAGERIE-A : inbox, création/réouverture fil privé, détail, archive, pin, mute."""

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.iam.helpers.compliance import close_gates
from apps.iam.helpers.mfa import login_until_jwt
from apps.iam.models import Role, User
from apps.messaging.models import BlockedUser, Conversation, ConversationMember

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


@pytest.fixture
def jean(user_role):
    return close_gates(
        User.objects.create_user(
            email="jean.dupont@yas.tg", password=PASSWORD, username="jean.dupont",
            role=user_role, first_name="Jean", last_name="Dupont",
        )
    )


@pytest.fixture
def marie(user_role):
    return close_gates(
        User.objects.create_user(
            email="marie.koevi@yas.tg", password=PASSWORD, username="marie.koevi",
            role=user_role, first_name="Marie", last_name="Koevi",
        )
    )


def _jwt(api, user, *, password=PASSWORD, device_uuid="web-1"):
    device = {"device_uuid": device_uuid, "platform": "WEB"}
    r = login_until_jwt(api, email=user.email, password=password, device=device)
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {r.data['data']['access_token']}")
    return r


# --- MSG-01/02/19 : créer / rouvrir un fil privé --------------------------------


@pytest.mark.django_db
def test_post_conversations_private_creates(api, jean, marie):
    _jwt(api, jean)
    r = api.post(
        "/api/v1/conversations", {"type": "PRIVATE", "participant_id": str(marie.id)}, format="json"
    )
    assert r.status_code == 201
    data = r.data["data"]
    assert data["encrypted"] is True
    conv = Conversation.objects.get(pk=data["id"])
    assert ConversationMember.objects.filter(conversation=conv, active=True).count() == 2


@pytest.mark.django_db
def test_post_conversations_same_pair_reopens(api, jean, marie):
    _jwt(api, jean)
    body = {"type": "PRIVATE", "participant_id": str(marie.id)}
    r1 = api.post("/api/v1/conversations", body, format="json")
    assert r1.status_code == 201
    r2 = api.post("/api/v1/conversations", body, format="json")
    assert r2.status_code == 200
    assert r2.data["data"]["id"] == r1.data["data"]["id"]
    assert Conversation.objects.count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize("bad_type", ["GROUP", "AI"])
def test_post_conversations_unsupported_type_rejected(api, jean, marie, bad_type):
    _jwt(api, jean)
    r = api.post(
        "/api/v1/conversations", {"type": bad_type, "participant_id": str(marie.id)}, format="json"
    )
    assert r.status_code == 400
    assert r.data["code"] == "VALIDATION_ERROR"


@pytest.mark.django_db
def test_post_conversations_self_rejected(api, jean):
    _jwt(api, jean)
    r = api.post(
        "/api/v1/conversations", {"type": "PRIVATE", "participant_id": str(jean.id)}, format="json"
    )
    assert r.status_code == 400
    assert r.data["code"] == "VALIDATION_ERROR"


@pytest.mark.django_db
def test_post_conversations_blocked_forbidden(api, jean, marie):
    BlockedUser.objects.create(blocker=marie, blocked=jean)
    _jwt(api, jean)
    r = api.post(
        "/api/v1/conversations", {"type": "PRIVATE", "participant_id": str(marie.id)}, format="json"
    )
    assert r.status_code == 403
    assert r.data["code"] == "USER_BLOCKED"


@pytest.mark.django_db
def test_post_conversations_unknown_participant_404(api, jean):
    _jwt(api, jean)
    r = api.post(
        "/api/v1/conversations",
        {"type": "PRIVATE", "participant_id": "11111111-1111-1111-1111-111111111111"},
        format="json",
    )
    assert r.status_code == 404


# --- MSG-04/15/16 : inbox --------------------------------------------------------


@pytest.mark.django_db
def test_get_inbox_lists_conversation(api, jean, marie):
    _jwt(api, jean)
    body = {"type": "PRIVATE", "participant_id": str(marie.id)}
    api.post("/api/v1/conversations", body, format="json")
    r = api.get("/api/v1/conversations")
    assert r.status_code == 200
    assert len(r.data["data"]["results"]) == 1
    assert r.data["data"]["results"][0]["peer_summary"]["user_id"] == str(marie.id)


@pytest.mark.django_db
def test_get_inbox_archived_filter(api, jean, marie):
    _jwt(api, jean)
    conv_id = api.post(
        "/api/v1/conversations", {"type": "PRIVATE", "participant_id": str(marie.id)}, format="json"
    ).data["data"]["id"]
    api.post(f"/api/v1/conversations/{conv_id}/archive")
    default_inbox = api.get("/api/v1/conversations")
    assert len(default_inbox.data["data"]["results"]) == 0
    archived_inbox = api.get("/api/v1/conversations?archived=true")
    assert len(archived_inbox.data["data"]["results"]) == 1


# --- MSG-11/18/03 : détail, deep-link -------------------------------------------


@pytest.mark.django_db
def test_get_conversation_detail_non_member_404(api, jean, marie, user_role):
    outsider = close_gates(
        User.objects.create_user(
            email="paul.outsider@yas.tg", password=PASSWORD, username="paul.outsider",
            role=user_role, first_name="Paul", last_name="Outsider",
        )
    )
    _jwt(api, jean)
    conv_id = api.post(
        "/api/v1/conversations", {"type": "PRIVATE", "participant_id": str(marie.id)}, format="json"
    ).data["data"]["id"]
    _jwt(api, outsider, device_uuid="web-outsider")
    r = api.get(f"/api/v1/conversations/{conv_id}")
    assert r.status_code == 404


@pytest.mark.django_db
def test_get_conversation_by_uuid_matches_detail(api, jean, marie):
    _jwt(api, jean)
    created = api.post(
        "/api/v1/conversations", {"type": "PRIVATE", "participant_id": str(marie.id)}, format="json"
    ).data["data"]
    by_id = api.get(f"/api/v1/conversations/{created['id']}")
    by_uuid = api.get(f"/api/v1/conversations/by-uuid/{created['conversation_uuid']}")
    assert by_uuid.status_code == 200
    assert by_uuid.data["data"]["id"] == by_id.data["data"]["id"]


# --- MSG-07/08 : archive / désarchive --------------------------------------------


@pytest.mark.django_db
def test_archive_then_unarchive_idempotent(api, jean, marie):
    _jwt(api, jean)
    conv_id = api.post(
        "/api/v1/conversations", {"type": "PRIVATE", "participant_id": str(marie.id)}, format="json"
    ).data["data"]["id"]
    r1 = api.post(f"/api/v1/conversations/{conv_id}/archive")
    assert r1.status_code == 200 and r1.data["data"]["archived"] is True
    r2 = api.post(f"/api/v1/conversations/{conv_id}/archive")  # idempotent
    assert r2.status_code == 200
    r3 = api.delete(f"/api/v1/conversations/{conv_id}/archive")
    assert r3.status_code == 200 and r3.data["data"]["archived"] is False


# --- MSG-09/10 : pin / mute -------------------------------------------------------


@pytest.mark.django_db
def test_patch_inbox_pin(api, jean, marie):
    _jwt(api, jean)
    conv_id = api.post(
        "/api/v1/conversations", {"type": "PRIVATE", "participant_id": str(marie.id)}, format="json"
    ).data["data"]["id"]
    r = api.patch(f"/api/v1/conversations/{conv_id}/inbox", {"pinned": True}, format="json")
    assert r.status_code == 200 and r.data["data"]["pinned"] is True
    inbox = api.get("/api/v1/conversations?pinned=true")
    assert len(inbox.data["data"]["results"]) == 1


@pytest.mark.django_db
def test_patch_settings_mute(api, jean, marie):
    _jwt(api, jean)
    conv_id = api.post(
        "/api/v1/conversations", {"type": "PRIVATE", "participant_id": str(marie.id)}, format="json"
    ).data["data"]["id"]
    r = api.patch(f"/api/v1/conversations/{conv_id}/settings", {"muted": True}, format="json")
    assert r.status_code == 200 and r.data["data"]["muted"] is True
    detail = api.get(f"/api/v1/conversations/{conv_id}")
    assert detail.data["data"]["settings"]["muted"] is True


# --- MSG-12 : messages épinglés (liste vide ce jour) -----------------------------


@pytest.mark.django_db
def test_get_pinned_messages_empty(api, jean, marie):
    _jwt(api, jean)
    conv_id = api.post(
        "/api/v1/conversations", {"type": "PRIVATE", "participant_id": str(marie.id)}, format="json"
    ).data["data"]["id"]
    r = api.get(f"/api/v1/conversations/{conv_id}/pinned-messages")
    assert r.status_code == 200
    assert r.data["data"]["results"] == []


# --- Auth / portes -----------------------------------------------------------------


@pytest.mark.django_db
def test_without_jwt_401(api, db):
    r = api.get("/api/v1/conversations")
    assert r.status_code == 401


@pytest.mark.django_db
def test_self_without_tos_403(api, user_role):
    fresh = User.objects.create_user(
        email="fresh.msg@yas.tg", password=PASSWORD, username="fresh.msg",
        role=user_role, first_name="Fresh", last_name="Msg",
    )
    _jwt(api, fresh)
    r = api.get("/api/v1/conversations")
    assert r.status_code == 403
    assert r.data["code"] == "TOS_REQUIRED"


@pytest.mark.django_db
def test_schema_has_messaging_paths(api, db):
    schema = api.get("/api/schema/")
    assert schema.status_code == 200
    text = schema.content.decode()
    assert "/api/v1/conversations" in text
