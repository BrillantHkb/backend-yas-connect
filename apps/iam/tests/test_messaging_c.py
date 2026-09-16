"""MESSAGERIE-C : groupes (création, métadonnées, réglages, membres, rôles, leave)."""

import base64

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.crypto.models import ConversationKey
from apps.iam.helpers.compliance import close_gates
from apps.iam.helpers.mfa import login_until_jwt
from apps.iam.models import PrivacySetting, Role, User
from apps.messaging.models import Conversation, ConversationMember

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
def paul(user_role):
    return _make_user(user_role, "paul.mensah@yas.tg", "paul.mensah", "Paul", "Mensah")


def _jwt(api, user, *, password=PASSWORD, device_uuid="web-1"):
    device = {"device_uuid": device_uuid, "platform": "WEB"}
    r = login_until_jwt(api, email=user.email, password=password, device=device)
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {r.data['data']['access_token']}")
    return r


def _create_group(api, title, member_ids, visibility="PRIVATE"):
    return api.post(
        "/api/v1/conversations",
        {
            "type": "GROUP",
            "title": title,
            "member_ids": [str(i) for i in member_ids],
            "visibility": visibility,
        },
        format="json",
    )


# --- MSG-41 : créer -----------------------------------------------------------


@pytest.mark.django_db
def test_create_group_success(api, jean, marie, paul):
    _jwt(api, jean)
    r = _create_group(api, "Equipe YAS", [marie.id, paul.id])
    assert r.status_code == 201
    conv_id = r.data["data"]["id"]
    conversation = Conversation.objects.get(pk=conv_id)
    assert conversation.owner_id == jean.id
    assert conversation.encrypted is False
    roles = dict(
        ConversationMember.objects.filter(conversation=conversation).values_list("user_id", "role")
    )
    assert roles[jean.id] == "OWNER"
    assert roles[marie.id] == "MEMBER"
    assert roles[paul.id] == "MEMBER"
    assert ConversationKey.objects.filter(conversation_id=conv_id).exists()


@pytest.mark.django_db
def test_create_group_skips_member_with_invites_disabled(api, jean, marie, paul):
    PrivacySetting.objects.update_or_create(user=paul, defaults={"allow_group_invites": False})
    _jwt(api, jean)
    r = _create_group(api, "Equipe YAS", [marie.id, paul.id])
    assert r.status_code == 201
    conv_id = r.data["data"]["id"]
    assert not ConversationMember.objects.filter(conversation_id=conv_id, user=paul).exists()
    assert ConversationMember.objects.filter(conversation_id=conv_id, user=marie).exists()


@pytest.mark.django_db
def test_create_group_all_invalid_400(api, jean, marie):
    PrivacySetting.objects.update_or_create(user=marie, defaults={"allow_group_invites": False})
    _jwt(api, jean)
    r = _create_group(api, "Vide", [marie.id])
    assert r.status_code == 400
    assert r.data["code"] == "VALIDATION_ERROR"


# --- MSG-42 : métadonnées ------------------------------------------------------


@pytest.mark.django_db
def test_patch_conversation_by_member_403(api, jean, marie, paul):
    _jwt(api, jean)
    conv_id = _create_group(api, "Equipe", [marie.id, paul.id]).data["data"]["id"]
    _jwt(api, marie)
    r = api.patch(f"/api/v1/conversations/{conv_id}", {"title": "Nouveau nom"}, format="json")
    assert r.status_code == 403


@pytest.mark.django_db
def test_patch_conversation_by_admin_200(api, jean, marie, paul):
    _jwt(api, jean)
    conv_id = _create_group(api, "Equipe", [marie.id, paul.id]).data["data"]["id"]
    api.patch(
        f"/api/v1/conversations/{conv_id}/members/{marie.id}", {"role": "ADMIN"}, format="json"
    )
    _jwt(api, marie)
    r = api.patch(f"/api/v1/conversations/{conv_id}", {"title": "Nouveau nom"}, format="json")
    assert r.status_code == 200
    assert r.data["data"]["title"] == "Nouveau nom"


# --- group-settings : locked --------------------------------------------------


@pytest.mark.django_db
def test_group_settings_locked_blocks_member_send(api, jean, marie, paul):
    _jwt(api, jean)
    conv_id = _create_group(api, "Equipe", [marie.id, paul.id]).data["data"]["id"]
    api.patch(f"/api/v1/conversations/{conv_id}/group-settings", {"locked": True}, format="json")
    _jwt(api, marie)
    body = {"type": "TEXT", "encrypted_content": base64.b64encode(b"hi").decode()}
    r = api.post(f"/api/v1/conversations/{conv_id}/messages", body, format="json")
    assert r.status_code == 403
    assert r.data["code"] == "CONVERSATION_LOCKED"


# --- MSG-44 : membres -----------------------------------------------------------


@pytest.mark.django_db
def test_get_members_lists_roles(api, jean, marie, paul):
    _jwt(api, jean)
    conv_id = _create_group(api, "Equipe", [marie.id, paul.id]).data["data"]["id"]
    r = api.get(f"/api/v1/conversations/{conv_id}/members")
    assert r.status_code == 200
    roles = {row["user_id"]: row["role"] for row in r.data["data"]["results"]}
    assert roles[str(jean.id)] == "OWNER"
    assert roles[str(marie.id)] == "MEMBER"


@pytest.mark.django_db
def test_add_member_group_full_409(api, jean, marie, paul):
    _jwt(api, jean)
    conv_id = _create_group(api, "Equipe", [marie.id]).data["data"]["id"]
    api.patch(f"/api/v1/conversations/{conv_id}/group-settings", {"max_members": 2}, format="json")
    r = api.post(
        f"/api/v1/conversations/{conv_id}/members", {"user_id": str(paul.id)}, format="json"
    )
    assert r.status_code == 409
    assert r.data["code"] == "GROUP_FULL"


@pytest.mark.django_db
def test_add_member_already_member_409(api, jean, marie, paul):
    _jwt(api, jean)
    conv_id = _create_group(api, "Equipe", [marie.id, paul.id]).data["data"]["id"]
    r = api.post(
        f"/api/v1/conversations/{conv_id}/members", {"user_id": str(marie.id)}, format="json"
    )
    assert r.status_code == 409
    assert r.data["code"] == "ALREADY_MEMBER"


# --- MSG-47/48 : rôles / transfert ------------------------------------------------


@pytest.mark.django_db
def test_transfer_ownership_by_owner(api, jean, marie, paul):
    _jwt(api, jean)
    conv_id = _create_group(api, "Equipe", [marie.id, paul.id]).data["data"]["id"]
    r = api.patch(
        f"/api/v1/conversations/{conv_id}/members/{marie.id}", {"role": "OWNER"}, format="json"
    )
    assert r.status_code == 200
    assert r.data["data"]["role"] == "OWNER"
    jean_role = ConversationMember.objects.get(conversation_id=conv_id, user=jean).role
    assert jean_role == "ADMIN"


@pytest.mark.django_db
def test_transfer_ownership_by_admin_403(api, jean, marie, paul):
    _jwt(api, jean)
    conv_id = _create_group(api, "Equipe", [marie.id, paul.id]).data["data"]["id"]
    api.patch(
        f"/api/v1/conversations/{conv_id}/members/{marie.id}", {"role": "ADMIN"}, format="json"
    )
    _jwt(api, marie)
    r = api.patch(
        f"/api/v1/conversations/{conv_id}/members/{paul.id}", {"role": "OWNER"}, format="json"
    )
    assert r.status_code == 403


# --- MSG-45 : retrait -------------------------------------------------------------


@pytest.mark.django_db
def test_remove_owner_403(api, jean, marie, paul):
    _jwt(api, jean)
    conv_id = _create_group(api, "Equipe", [marie.id, paul.id]).data["data"]["id"]
    r = api.delete(f"/api/v1/conversations/{conv_id}/members/{jean.id}")
    assert r.status_code == 403


@pytest.mark.django_db
def test_admin_cannot_remove_other_admin_403(api, jean, marie, paul):
    _jwt(api, jean)
    conv_id = _create_group(api, "Equipe", [marie.id, paul.id]).data["data"]["id"]
    api.patch(
        f"/api/v1/conversations/{conv_id}/members/{marie.id}", {"role": "ADMIN"}, format="json"
    )
    api.patch(
        f"/api/v1/conversations/{conv_id}/members/{paul.id}", {"role": "ADMIN"}, format="json"
    )
    _jwt(api, marie)
    r = api.delete(f"/api/v1/conversations/{conv_id}/members/{paul.id}")
    assert r.status_code == 403


# --- MSG-46 : quitter --------------------------------------------------------------


@pytest.mark.django_db
def test_leave_owner_403(api, jean, marie, paul):
    _jwt(api, jean)
    conv_id = _create_group(api, "Equipe", [marie.id, paul.id]).data["data"]["id"]
    r = api.post(f"/api/v1/conversations/{conv_id}/leave")
    assert r.status_code == 403
    assert r.data["code"] == "OWNER_MUST_TRANSFER"


@pytest.mark.django_db
def test_leave_member_200(api, jean, marie, paul):
    _jwt(api, jean)
    conv_id = _create_group(api, "Equipe", [marie.id, paul.id]).data["data"]["id"]
    _jwt(api, marie)
    r = api.post(f"/api/v1/conversations/{conv_id}/leave")
    assert r.status_code == 200
    member = ConversationMember.objects.get(conversation_id=conv_id, user=marie)
    assert member.active is False
    assert member.left_at is not None


# --- Envoi/lecture GROUP : chiffrement clé de fil, aucune garde crypto ------------


@pytest.mark.django_db
def test_send_group_message_no_crypto_guard(api, jean, marie, paul):
    _jwt(api, jean)  # jean n'a publié aucune clé Signal — ne doit pas bloquer un GROUP
    conv_id = _create_group(api, "Equipe", [marie.id, paul.id]).data["data"]["id"]
    body = {"type": "TEXT", "encrypted_content": base64.b64encode(b"hello group").decode()}
    r = api.post(f"/api/v1/conversations/{conv_id}/messages", body, format="json")
    assert r.status_code == 201

    r2 = api.get(f"/api/v1/messages/{r.data['data']['id']}")
    assert r2.status_code == 200
    decoded = base64.b64decode(r2.data["data"]["encrypted_content"])
    assert decoded == b"hello group"


@pytest.mark.django_db
def test_schema_has_group_paths(api, db):
    schema = api.get("/api/schema/")
    assert schema.status_code == 200
    text = schema.content.decode()
    assert "/api/v1/conversations" in text
    assert "members" in text
