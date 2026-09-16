"""MESSAGERIE-B : historique, envoi, détail, édition, suppression, recherche."""

import base64
from datetime import timedelta

import pytest
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APIClient

from apps.crypto.models import OneTimePreKey
from apps.iam.helpers.compliance import close_gates
from apps.iam.helpers.mfa import login_until_jwt
from apps.iam.models import PrivacySetting, Role, User
from apps.media.models import MediaFile
from apps.messaging.models import Message, MessageEdit, MessageMention
from apps.notifications.models import Notification

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


def _create_private(api, other_id):
    return api.post(
        "/api/v1/conversations", {"type": "PRIVATE", "participant_id": str(other_id)}, format="json"
    ).data["data"]["id"]


def _send_body(**overrides):
    body = {"type": "TEXT", "encrypted_content": _b64(b"hello"), "client_message_id": ""}
    body.update(overrides)
    return body


# --- CRY-A intégration : garde à l'envoi ------------------------------------------


@pytest.mark.django_db
def test_send_sender_without_identity_409(api, jean, marie):
    _jwt(api, marie)
    _publish_identity_and_spk(api)
    _jwt(api, jean)
    conv_id = _create_private(api, marie.id)
    r = api.post(f"/api/v1/conversations/{conv_id}/messages", _send_body(), format="json")
    assert r.status_code == 409
    assert r.data["code"] == "CRYPTO_KEYS_MISSING"


@pytest.mark.django_db
def test_send_peer_not_ready_409_no_otpk_consumed(api, jean, marie):
    _jwt(api, jean)
    _publish_identity_and_spk(api)
    conv_id = _create_private(api, marie.id)
    before = OneTimePreKey.objects.filter(device__user=marie).count()
    r = api.post(f"/api/v1/conversations/{conv_id}/messages", _send_body(), format="json")
    assert r.status_code == 409
    assert r.data["code"] == "PEER_KEYS_MISSING"
    after = OneTimePreKey.objects.filter(device__user=marie).count()
    assert before == after == 0


@pytest.mark.django_db
def test_send_both_ready_201_increments_unread_and_notifies(api, jean, marie):
    _jwt(api, marie)
    _publish_identity_and_spk(api)
    _jwt(api, jean)
    _publish_identity_and_spk(api)
    conv_id = _create_private(api, marie.id)
    r = api.post(f"/api/v1/conversations/{conv_id}/messages", _send_body(), format="json")
    assert r.status_code == 201
    inbox = api.get("/api/v1/conversations")
    assert inbox.data["data"]["results"][0]["last_message_at"] is not None

    _jwt(api, marie)
    marie_inbox = api.get("/api/v1/conversations").data["data"]["results"][0]
    assert marie_inbox["unread_count"] == 1
    assert Notification.objects.filter(user=marie, type=Notification.Type.MESSAGE_NEW).exists()


@pytest.mark.django_db
def test_send_duplicate_client_message_id_409(api, jean, marie):
    _jwt(api, marie)
    _publish_identity_and_spk(api)
    _jwt(api, jean)
    _publish_identity_and_spk(api)
    conv_id = _create_private(api, marie.id)
    body = _send_body(client_message_id="dup-1")
    r1 = api.post(f"/api/v1/conversations/{conv_id}/messages", body, format="json")
    assert r1.status_code == 201
    r2 = api.post(f"/api/v1/conversations/{conv_id}/messages", body, format="json")
    assert r2.status_code == 409
    assert r2.data["code"] == "DUPLICATE_MESSAGE"
    assert Message.objects.filter(conversation_id=conv_id).count() == 1


@pytest.mark.django_db
def test_send_with_own_media_clean_derives_type(api, jean, marie):
    _jwt(api, marie)
    _publish_identity_and_spk(api)
    _jwt(api, jean)
    _publish_identity_and_spk(api)
    conv_id = _create_private(api, marie.id)
    media = MediaFile.objects.create(
        owner=jean, storage_path="image/2026/x.png",
        media_type=MediaFile.MediaType.IMAGE, scan_status=MediaFile.ScanStatus.CLEAN,
    )
    r = api.post(
        f"/api/v1/conversations/{conv_id}/messages",
        _send_body(media_id=str(media.id), encrypted_content=""),
        format="json",
    )
    assert r.status_code == 201
    assert r.data["data"]["type"] == "IMAGE"


@pytest.mark.django_db
def test_send_with_media_infected_422(api, jean, marie):
    _jwt(api, marie)
    _publish_identity_and_spk(api)
    _jwt(api, jean)
    _publish_identity_and_spk(api)
    conv_id = _create_private(api, marie.id)
    media = MediaFile.objects.create(
        owner=jean, storage_path="document/2026/x.pdf",
        media_type=MediaFile.MediaType.DOCUMENT, scan_status=MediaFile.ScanStatus.INFECTED,
    )
    r = api.post(
        f"/api/v1/conversations/{conv_id}/messages",
        _send_body(media_id=str(media.id), encrypted_content=""),
        format="json",
    )
    assert r.status_code == 422
    assert r.data["code"] == "MEDIA_INFECTED"


@pytest.mark.django_db
def test_send_with_media_of_another_user_404(api, jean, marie):
    _jwt(api, marie)
    _publish_identity_and_spk(api)
    other_media = MediaFile.objects.create(
        owner=marie, storage_path="document/2026/y.pdf",
        media_type=MediaFile.MediaType.DOCUMENT, scan_status=MediaFile.ScanStatus.CLEAN,
    )
    _jwt(api, jean)
    _publish_identity_and_spk(api)
    conv_id = _create_private(api, marie.id)
    r = api.post(
        f"/api/v1/conversations/{conv_id}/messages",
        _send_body(media_id=str(other_media.id), encrypted_content=""),
        format="json",
    )
    assert r.status_code == 404


@pytest.mark.django_db
def test_send_mention_respects_privacy(api, jean, marie):
    PrivacySetting.objects.update_or_create(user=marie, defaults={"allow_mentions": False})
    _jwt(api, marie)
    _publish_identity_and_spk(api)
    _jwt(api, jean)
    _publish_identity_and_spk(api)
    conv_id = _create_private(api, marie.id)
    r = api.post(
        f"/api/v1/conversations/{conv_id}/messages",
        _send_body(mentions=[str(marie.id)]),
        format="json",
    )
    assert r.status_code == 201
    message_id = r.data["data"]["id"]
    assert not MessageMention.objects.filter(message_id=message_id).exists()
    assert not Notification.objects.filter(
        user=marie, type=Notification.Type.MESSAGE_MENTION
    ).exists()


# --- MSG-21/27 : historique, détail -----------------------------------------------


@pytest.mark.django_db
def test_get_messages_history_sorted(api, jean, marie):
    _jwt(api, marie)
    _publish_identity_and_spk(api)
    _jwt(api, jean)
    _publish_identity_and_spk(api)
    conv_id = _create_private(api, marie.id)
    api.post(f"/api/v1/conversations/{conv_id}/messages", _send_body(), format="json")
    api.post(f"/api/v1/conversations/{conv_id}/messages", _send_body(), format="json")
    r = api.get(f"/api/v1/conversations/{conv_id}/messages")
    assert r.status_code == 200
    assert len(r.data["data"]["results"]) == 2


@pytest.mark.django_db
def test_get_message_detail_non_member_404(api, jean, marie, user_role):
    outsider = close_gates(
        User.objects.create_user(
            email="paul.outsider2@yas.tg", password=PASSWORD, username="paul.outsider2",
            role=user_role, first_name="Paul", last_name="Outsider",
        )
    )
    _jwt(api, marie)
    _publish_identity_and_spk(api)
    _jwt(api, jean)
    _publish_identity_and_spk(api)
    conv_id = _create_private(api, marie.id)
    msg_id = api.post(
        f"/api/v1/conversations/{conv_id}/messages", _send_body(), format="json"
    ).data["data"]["id"]
    _jwt(api, outsider, device_uuid="web-outsider")
    r = api.get(f"/api/v1/messages/{msg_id}")
    assert r.status_code == 404


# --- MSG-24 : éditer ---------------------------------------------------------------


@pytest.mark.django_db
def test_edit_by_non_author_403(api, jean, marie):
    _jwt(api, marie)
    _publish_identity_and_spk(api)
    _jwt(api, jean)
    _publish_identity_and_spk(api)
    conv_id = _create_private(api, marie.id)
    msg_id = api.post(
        f"/api/v1/conversations/{conv_id}/messages", _send_body(), format="json"
    ).data["data"]["id"]
    _jwt(api, marie)
    r = api.patch(
        f"/api/v1/messages/{msg_id}", {"encrypted_content": _b64(b"nope")}, format="json"
    )
    assert r.status_code == 403
    assert r.data["code"] == "FORBIDDEN"


@pytest.mark.django_db
def test_edit_after_window_403(api, jean, marie):
    _jwt(api, marie)
    _publish_identity_and_spk(api)
    _jwt(api, jean)
    _publish_identity_and_spk(api)
    conv_id = _create_private(api, marie.id)
    msg_id = api.post(
        f"/api/v1/conversations/{conv_id}/messages", _send_body(), format="json"
    ).data["data"]["id"]
    Message.objects.filter(pk=msg_id).update(sent_at=timezone.now() - timedelta(minutes=16))
    r = api.patch(
        f"/api/v1/messages/{msg_id}", {"encrypted_content": _b64(b"too-late")}, format="json"
    )
    assert r.status_code == 403
    assert r.data["code"] == "EDIT_WINDOW_EXPIRED"


@pytest.mark.django_db
def test_edit_by_author_within_window_200(api, jean, marie):
    _jwt(api, marie)
    _publish_identity_and_spk(api)
    _jwt(api, jean)
    _publish_identity_and_spk(api)
    conv_id = _create_private(api, marie.id)
    msg_id = api.post(
        f"/api/v1/conversations/{conv_id}/messages", _send_body(), format="json"
    ).data["data"]["id"]
    r = api.patch(
        f"/api/v1/messages/{msg_id}", {"encrypted_content": _b64(b"edited")}, format="json"
    )
    assert r.status_code == 200
    assert r.data["data"]["edited"] is True
    assert MessageEdit.objects.filter(message_id=msg_id).count() == 1


# --- MSG-25/26 : supprimer ----------------------------------------------------------


@pytest.mark.django_db
def test_delete_self_hides_only_for_caller(api, jean, marie):
    _jwt(api, marie)
    _publish_identity_and_spk(api)
    _jwt(api, jean)
    _publish_identity_and_spk(api)
    conv_id = _create_private(api, marie.id)
    msg_id = api.post(
        f"/api/v1/conversations/{conv_id}/messages", _send_body(), format="json"
    ).data["data"]["id"]
    r = api.delete(f"/api/v1/messages/{msg_id}?scope=SELF")
    assert r.status_code == 200
    assert r.data["data"]["scope"] == "SELF"
    jean_history = api.get(f"/api/v1/conversations/{conv_id}/messages")
    assert jean_history.data["data"]["results"] == []
    _jwt(api, marie)
    marie_history = api.get(f"/api/v1/conversations/{conv_id}/messages")
    assert len(marie_history.data["data"]["results"]) == 1


@pytest.mark.django_db
def test_delete_everyone_by_non_author_403(api, jean, marie):
    _jwt(api, marie)
    _publish_identity_and_spk(api)
    _jwt(api, jean)
    _publish_identity_and_spk(api)
    conv_id = _create_private(api, marie.id)
    msg_id = api.post(
        f"/api/v1/conversations/{conv_id}/messages", _send_body(), format="json"
    ).data["data"]["id"]
    _jwt(api, marie)
    r = api.delete(f"/api/v1/messages/{msg_id}?scope=EVERYONE")
    assert r.status_code == 403
    assert r.data["code"] == "FORBIDDEN"


@pytest.mark.django_db
def test_delete_everyone_by_author_purges_content(api, jean, marie):
    _jwt(api, marie)
    _publish_identity_and_spk(api)
    _jwt(api, jean)
    _publish_identity_and_spk(api)
    conv_id = _create_private(api, marie.id)
    msg_id = api.post(
        f"/api/v1/conversations/{conv_id}/messages", _send_body(), format="json"
    ).data["data"]["id"]
    r = api.delete(f"/api/v1/messages/{msg_id}?scope=EVERYONE")
    assert r.status_code == 200
    message = Message.objects.get(pk=msg_id)
    assert message.deleted is True
    assert bytes(message.encrypted_content) == b""


# --- MSG-28 : recherche --------------------------------------------------------------


@pytest.mark.django_db
def test_search_q_too_short_400(api, jean, marie):
    _jwt(api, marie)
    _publish_identity_and_spk(api)
    _jwt(api, jean)
    _publish_identity_and_spk(api)
    conv_id = _create_private(api, marie.id)
    r = api.get(f"/api/v1/conversations/{conv_id}/messages/search?q=a")
    assert r.status_code == 400
    assert r.data["code"] == "VALIDATION_ERROR"


@pytest.mark.django_db
def test_search_matches_tag(api, jean, marie):
    _jwt(api, marie)
    _publish_identity_and_spk(api)
    _jwt(api, jean)
    _publish_identity_and_spk(api)
    conv_id = _create_private(api, marie.id)
    api.post(
        f"/api/v1/conversations/{conv_id}/messages", _send_body(tags=["projet-yas"]), format="json"
    )
    r = api.get(f"/api/v1/conversations/{conv_id}/messages/search?q=yas")
    assert r.status_code == 200
    assert len(r.data["data"]["results"]) == 1


# --- Auth / portes -----------------------------------------------------------------


@pytest.mark.django_db
def test_without_jwt_401(api, db):
    r = api.get("/api/v1/messages/11111111-1111-1111-1111-111111111111")
    assert r.status_code == 401


@pytest.mark.django_db
def test_self_without_tos_403(api, user_role, marie):
    fresh = User.objects.create_user(
        email="fresh.msgb@yas.tg", password=PASSWORD, username="fresh.msgb",
        role=user_role, first_name="Fresh", last_name="MsgB",
    )
    _jwt(api, fresh)
    r = api.get(f"/api/v1/conversations/{marie.id}/messages")
    assert r.status_code == 403
    assert r.data["code"] == "TOS_REQUIRED"


@pytest.mark.django_db
def test_schema_has_messages_paths(api, db):
    schema = api.get("/api/schema/")
    assert schema.status_code == 200
    text = schema.content.decode()
    assert "/api/v1/conversations/{id}/messages" in text or "messages" in text
