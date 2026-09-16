"""MESSAGERIE-E (partiel) : réactions, transfert, signets, sondages GROUP."""

import base64

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.iam.helpers.compliance import close_gates
from apps.iam.helpers.mfa import login_until_jwt
from apps.iam.models import Role, User
from apps.messaging.models import MessageReaction

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


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode()


def _publish_identity_and_spk(api, *, key_id=1):
    api.put(
        "/api/v1/crypto/me/identity",
        {"registration_id": 111, "identity_public_key": _b64(b"identity-key-32-bytes-padding!!!")},
        format="json",
    )
    api.put(
        "/api/v1/crypto/me/signed-prekey",
        {"key_id": key_id, "public_key": _b64(b"spk-pub"), "signature": _b64(b"spk-sig")},
        format="json",
    )


def _create_group(api, title, member_ids):
    return api.post(
        "/api/v1/conversations",
        {"type": "GROUP", "title": title, "member_ids": [str(i) for i in member_ids]},
        format="json",
    ).data["data"]["id"]


def _create_private(api, other_id):
    return api.post(
        "/api/v1/conversations", {"type": "PRIVATE", "participant_id": str(other_id)}, format="json"
    ).data["data"]["id"]


def _send(api, conv_id, text=b"hi"):
    body = {"type": "TEXT", "encrypted_content": _b64(text)}
    return api.post(f"/api/v1/conversations/{conv_id}/messages", body, format="json").data["data"]


def _send_poll(api, conv_id, question="Qui vient ?", options=("Oui", "Non"), multiple=False):
    body = {
        "type": "POLL",
        "poll": {"question": question, "options": list(options), "multiple_choices": multiple},
    }
    return api.post(f"/api/v1/conversations/{conv_id}/messages", body, format="json")


# --- MSG-73/74 : réactions ---------------------------------------------------------


@pytest.mark.django_db
def test_reaction_idempotent(api, jean, marie):
    _jwt(api, jean)
    conv_id = _create_group(api, "Equipe", [marie.id])
    message = _send(api, conv_id)
    r1 = api.post(f"/api/v1/messages/{message['id']}/reactions", {"emoji": "👍"}, format="json")
    assert r1.status_code == 201
    r2 = api.post(f"/api/v1/messages/{message['id']}/reactions", {"emoji": "👍"}, format="json")
    assert r2.status_code == 201
    assert MessageReaction.objects.filter(message_id=message["id"]).count() == 1


@pytest.mark.django_db
def test_reaction_remove_idempotent(api, jean, marie):
    _jwt(api, jean)
    conv_id = _create_group(api, "Equipe", [marie.id])
    message = _send(api, conv_id)
    api.post(f"/api/v1/messages/{message['id']}/reactions", {"emoji": "👍"}, format="json")
    r1 = api.delete(f"/api/v1/messages/{message['id']}/reactions?emoji=%F0%9F%91%8D")
    assert r1.status_code == 200
    r2 = api.delete(f"/api/v1/messages/{message['id']}/reactions?emoji=%F0%9F%91%8D")
    assert r2.status_code == 200
    assert not MessageReaction.objects.filter(message_id=message["id"]).exists()


# --- MSG-75/76 : transfert ----------------------------------------------------------


@pytest.mark.django_db
def test_forward_group_to_group_no_body(api, jean, marie, paul):
    _jwt(api, jean)
    conv1 = _create_group(api, "Source", [marie.id])
    conv2 = _create_group(api, "Cible", [paul.id])
    message = _send(api, conv1, b"contenu original")
    r = api.post(
        f"/api/v1/messages/{message['id']}/forward", {"conversation_id": conv2}, format="json"
    )
    assert r.status_code == 201
    assert r.data["data"]["forwarded"] is True
    decoded = base64.b64decode(r.data["data"]["encrypted_content"])
    assert decoded == b"contenu original"


@pytest.mark.django_db
def test_forward_private_to_group_requires_body(api, jean, marie, paul):
    _jwt(api, marie)
    _publish_identity_and_spk(api)
    _jwt(api, jean)
    _publish_identity_and_spk(api)
    conv1 = _create_private(api, marie.id)
    conv2 = _create_group(api, "Cible", [paul.id])
    message = _send(api, conv1, b"secret prive")
    r = api.post(
        f"/api/v1/messages/{message['id']}/forward", {"conversation_id": conv2}, format="json"
    )
    assert r.status_code == 400
    assert r.data["code"] == "VALIDATION_ERROR"


@pytest.mark.django_db
def test_forward_with_content_provided(api, jean, marie, paul):
    _jwt(api, marie)
    _publish_identity_and_spk(api)
    _jwt(api, jean)
    _publish_identity_and_spk(api)
    conv1 = _create_private(api, marie.id)
    conv2 = _create_group(api, "Cible", [paul.id])
    message = _send(api, conv1, b"secret prive")
    r = api.post(
        f"/api/v1/messages/{message['id']}/forward",
        {"conversation_id": conv2, "encrypted_content": _b64(b"recopie cote client")},
        format="json",
    )
    assert r.status_code == 201
    decoded = base64.b64decode(r.data["data"]["encrypted_content"])
    assert decoded == b"recopie cote client"


# --- MSG-79/80 : signets -------------------------------------------------------------


@pytest.mark.django_db
def test_bookmark_then_list(api, jean, marie):
    _jwt(api, jean)
    conv_id = _create_group(api, "Equipe", [marie.id])
    message = _send(api, conv_id)
    r = api.post(
        f"/api/v1/messages/{message['id']}/bookmarks", {"note": "important"}, format="json"
    )
    assert r.status_code == 201
    listed = api.get("/api/v1/me/message-bookmarks")
    assert listed.status_code == 200
    assert listed.data["data"]["results"][0]["note"] == "important"


@pytest.mark.django_db
def test_bookmark_remove(api, jean, marie):
    _jwt(api, jean)
    conv_id = _create_group(api, "Equipe", [marie.id])
    message = _send(api, conv_id)
    api.post(f"/api/v1/messages/{message['id']}/bookmarks", {}, format="json")
    r = api.delete(f"/api/v1/messages/{message['id']}/bookmarks")
    assert r.status_code == 200
    listed = api.get("/api/v1/me/message-bookmarks")
    assert listed.data["data"]["results"] == []


# --- MSG-81/82/83 : sondages -----------------------------------------------------------


@pytest.mark.django_db
def test_poll_on_private_forbidden(api, jean, marie):
    _jwt(api, marie)
    _publish_identity_and_spk(api)
    _jwt(api, jean)
    _publish_identity_and_spk(api)
    conv_id = _create_private(api, marie.id)
    r = _send_poll(api, conv_id)
    assert r.status_code == 400
    assert r.data["code"] == "POLL_PRIVATE_FORBIDDEN"


@pytest.mark.django_db
def test_poll_on_group_created(api, jean, marie):
    _jwt(api, jean)
    conv_id = _create_group(api, "Equipe", [marie.id])
    r = _send_poll(api, conv_id)
    assert r.status_code == 201
    poll = r.data["data"]["poll"]
    assert poll["question"] == "Qui vient ?"
    assert len(poll["options"]) == 2


@pytest.mark.django_db
def test_poll_vote_single_choice_too_many_options_400(api, jean, marie):
    _jwt(api, jean)
    conv_id = _create_group(api, "Equipe", [marie.id])
    poll = _send_poll(api, conv_id).data["data"]["poll"]
    option_ids = [o["id"] for o in poll["options"]]
    r = api.post(f"/api/v1/polls/{poll['id']}/votes", {"option_ids": option_ids}, format="json")
    assert r.status_code == 400


@pytest.mark.django_db
def test_poll_vote_revote_updates_count(api, jean, marie):
    _jwt(api, jean)
    conv_id = _create_group(api, "Equipe", [marie.id])
    poll = _send_poll(api, conv_id).data["data"]["poll"]
    oui_id, non_id = poll["options"][0]["id"], poll["options"][1]["id"]
    api.post(f"/api/v1/polls/{poll['id']}/votes", {"option_ids": [oui_id]}, format="json")
    r = api.post(f"/api/v1/polls/{poll['id']}/votes", {"option_ids": [non_id]}, format="json")
    assert r.status_code == 200
    assert r.data["data"]["option_ids"] == [non_id]


@pytest.mark.django_db
def test_poll_vote_on_closed_403(api, jean, marie):
    _jwt(api, jean)
    conv_id = _create_group(api, "Equipe", [marie.id])
    poll = _send_poll(api, conv_id).data["data"]["poll"]
    api.post(f"/api/v1/polls/{poll['id']}/close")
    option_id = poll["options"][0]["id"]
    r = api.post(f"/api/v1/polls/{poll['id']}/votes", {"option_ids": [option_id]}, format="json")
    assert r.status_code == 403
    assert r.data["code"] == "POLL_CLOSED"


@pytest.mark.django_db
def test_poll_close_by_non_privileged_403(api, jean, marie, paul):
    _jwt(api, jean)
    conv_id = _create_group(api, "Equipe", [marie.id, paul.id])
    poll = _send_poll(api, conv_id).data["data"]["poll"]
    _jwt(api, marie)
    r = api.post(f"/api/v1/polls/{poll['id']}/close")
    assert r.status_code == 403


@pytest.mark.django_db
def test_poll_close_by_owner_200(api, jean, marie):
    _jwt(api, jean)
    conv_id = _create_group(api, "Equipe", [marie.id])
    poll = _send_poll(api, conv_id).data["data"]["poll"]
    r = api.post(f"/api/v1/polls/{poll['id']}/close")
    assert r.status_code == 200
    assert r.data["data"]["closed_at"] is not None


@pytest.mark.django_db
def test_schema_has_poll_paths(api, db):
    schema = api.get("/api/schema/")
    assert schema.status_code == 200
    text = schema.content.decode()
    assert "polls" in text
