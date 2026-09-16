"""CRYPTO-R + CRYPTO-A : bundles de clés Signal par appareil, ensure_conversation_key."""

import base64
import uuid

import pytest
from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APIClient

from apps.crypto.models import IdentityKey, OneTimePreKey, SignedPreKey
from apps.crypto.services.key_service import (
    ensure_conversation_key,
    require_peer_ready,
    require_sender_identity,
)
from apps.iam.helpers.compliance import close_gates
from apps.iam.helpers.mfa import login_until_jwt
from apps.iam.models import Device, Role, User
from apps.iam.services.device_service import revoke_device

PASSWORD = "Secret123!"
DEVICE = {"device_uuid": "test-web-1", "platform": "WEB"}
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


def _jwt(api, user, *, password=PASSWORD, device=DEVICE):
    r = login_until_jwt(api, email=user.email, password=password, device=device)
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {r.data['data']['access_token']}")
    return r


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode()


def _publish_full_bundle(api, *, key_id=1, otpk_ids=(1, 2)):
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
    keys = [{"key_id": i, "public_key": _b64(f"otpk-{i}".encode())} for i in otpk_ids]
    api.put("/api/v1/crypto/me/one-time-prekeys", {"keys": keys}, format="json")


# --- CRY-01 : identity ----------------------------------------------------------


@pytest.mark.django_db
def test_put_identity_upserts(api, jean):
    _jwt(api, jean)
    body = {"registration_id": 111, "identity_public_key": _b64(b"key-a")}
    r1 = api.put("/api/v1/crypto/me/identity", body, format="json")
    assert r1.status_code == 200
    body2 = {"registration_id": 222, "identity_public_key": _b64(b"key-b")}
    r2 = api.put("/api/v1/crypto/me/identity", body2, format="json")
    assert r2.status_code == 200
    device = Device.objects.get(user=jean, device_uuid=DEVICE["device_uuid"])
    assert IdentityKey.objects.filter(device=device).count() == 1
    assert IdentityKey.objects.get(device=device).registration_id == 222


@pytest.mark.django_db
def test_put_identity_invalid_base64(api, jean):
    _jwt(api, jean)
    r = api.put(
        "/api/v1/crypto/me/identity",
        {"registration_id": 1, "identity_public_key": "not-base64!!"},
        format="json",
    )
    assert r.status_code == 400
    assert r.data["code"] == "VALIDATION_ERROR"


# --- CRY-02 : signed prekey -------------------------------------------------------


@pytest.mark.django_db
def test_put_signed_prekey_same_key_id_replaces(api, jean):
    _jwt(api, jean)
    api.put(
        "/api/v1/crypto/me/signed-prekey",
        {"key_id": 1, "public_key": _b64(b"a"), "signature": _b64(b"sig-a")},
        format="json",
    )
    r = api.put(
        "/api/v1/crypto/me/signed-prekey",
        {"key_id": 1, "public_key": _b64(b"b"), "signature": _b64(b"sig-b")},
        format="json",
    )
    assert r.status_code == 200
    device = Device.objects.get(user=jean, device_uuid=DEVICE["device_uuid"])
    assert SignedPreKey.objects.filter(device=device, key_id=1).count() == 1
    assert bytes(SignedPreKey.objects.get(device=device, key_id=1).public_key) == b"b"


# --- CRY-03/04 : OTPK batch + count -----------------------------------------------


@pytest.mark.django_db
def test_otpk_batch_accept_then_skip(api, jean):
    _jwt(api, jean)
    keys = [{"key_id": i, "public_key": _b64(f"k{i}".encode())} for i in range(5)]
    r1 = api.put("/api/v1/crypto/me/one-time-prekeys", {"keys": keys}, format="json")
    assert r1.status_code == 200
    assert r1.data["data"] == {"accepted": 5, "skipped": 0}

    r2 = api.put("/api/v1/crypto/me/one-time-prekeys", {"keys": keys}, format="json")
    assert r2.data["data"] == {"accepted": 0, "skipped": 5}


@pytest.mark.django_db
def test_otpk_batch_over_100_rejected(api, jean):
    _jwt(api, jean)
    keys = [{"key_id": i, "public_key": _b64(b"k")} for i in range(101)]
    r = api.put("/api/v1/crypto/me/one-time-prekeys", {"keys": keys}, format="json")
    assert r.status_code == 400
    assert r.data["code"] == "VALIDATION_ERROR"


@pytest.mark.django_db
def test_otpk_count(api, jean):
    _jwt(api, jean)
    keys = [{"key_id": i, "public_key": _b64(f"k{i}".encode())} for i in range(3)]
    api.put("/api/v1/crypto/me/one-time-prekeys", {"keys": keys}, format="json")
    r = api.get("/api/v1/crypto/me/one-time-prekeys/count")
    assert r.status_code == 200
    assert r.data["data"]["available"] == 3


# --- CRY-05/06/14 : bundles --------------------------------------------------------


@pytest.mark.django_db
def test_get_bundles_success_consumes_otpk(api, jean, marie):
    _jwt(api, marie)
    _publish_full_bundle(api, otpk_ids=(1, 2))

    _jwt(api, jean)
    r1 = api.get(f"/api/v1/crypto/users/{marie.id}/bundles")
    assert r1.status_code == 200
    bundles = r1.data["data"]["bundles"]
    assert len(bundles) == 1
    first_otpk = bundles[0]["one_time_prekey"]
    assert first_otpk is not None

    r2 = api.get(f"/api/v1/crypto/users/{marie.id}/bundles")
    second_otpk = r2.data["data"]["bundles"][0]["one_time_prekey"]
    assert second_otpk is not None
    assert second_otpk["key_id"] != first_otpk["key_id"]

    r3 = api.get(f"/api/v1/crypto/users/{marie.id}/bundles")
    assert r3.data["data"]["bundles"][0]["one_time_prekey"] is None


@pytest.mark.django_db
def test_get_bundles_peer_keys_missing(api, jean, marie):
    _jwt(api, jean)
    r = api.get(f"/api/v1/crypto/users/{marie.id}/bundles")
    assert r.status_code == 409
    assert r.data["code"] == "PEER_KEYS_MISSING"


@pytest.mark.django_db
def test_get_bundles_unknown_user_404(api, jean):
    _jwt(api, jean)
    r = api.get(f"/api/v1/crypto/users/{uuid.uuid4()}/bundles")
    assert r.status_code == 404


@pytest.mark.django_db
def test_bundle_excludes_device_without_signed_prekey(api, jean, marie):
    _jwt(api, marie)
    api.put(
        "/api/v1/crypto/me/identity",
        {"registration_id": 1, "identity_public_key": _b64(b"id-only")},
        format="json",
    )
    _jwt(api, jean)
    r = api.get(f"/api/v1/crypto/users/{marie.id}/bundles")
    assert r.status_code == 409
    assert r.data["code"] == "PEER_KEYS_MISSING"


# --- Hooks internes (pas de route) -------------------------------------------------


@pytest.mark.django_db
def test_ensure_conversation_key_idempotent():
    conversation_id = uuid.uuid4()
    row1 = ensure_conversation_key(conversation_id)
    row2 = ensure_conversation_key(conversation_id)
    assert row1.id == row2.id
    assert row1.version == 1


@pytest.mark.django_db
def test_ensure_conversation_key_master_unset():
    with override_settings(CRYPTO_MASTER_KEY=""):
        with pytest.raises(Exception) as exc:
            ensure_conversation_key(uuid.uuid4())
        assert exc.value.code == "CRYPTO_MASTER_UNSET"


@pytest.mark.django_db
def test_require_sender_identity_missing(jean):
    device = Device.objects.create(
        user=jean, device_uuid="no-identity", platform=Device.Platform.ANDROID
    )
    with pytest.raises(Exception) as exc:
        require_sender_identity(device=device)
    assert exc.value.code == "CRYPTO_KEYS_MISSING"


# --- Delta MESSAGERIE-B : garde destinataire (jour 25) ------------------------------


@pytest.mark.django_db
def test_require_peer_ready_ok(api, marie):
    _jwt(api, marie)
    _publish_full_bundle(api)
    require_peer_ready(target_user=marie)  # ne lève rien


@pytest.mark.django_db
def test_require_peer_ready_missing_spk(api, marie):
    _jwt(api, marie)
    api.put(
        "/api/v1/crypto/me/identity",
        {"registration_id": 1, "identity_public_key": _b64(b"id-only")},
        format="json",
    )
    with pytest.raises(Exception) as exc:
        require_peer_ready(target_user=marie)
    assert exc.value.code == "PEER_KEYS_MISSING"


@pytest.mark.django_db
def test_require_peer_ready_never_consumes_otpk(api, marie):
    _jwt(api, marie)
    _publish_full_bundle(api, otpk_ids=(1, 2))
    device = Device.objects.get(user=marie, device_uuid=DEVICE["device_uuid"])
    before = OneTimePreKey.objects.filter(device=device, consumed_at__isnull=True).count()
    require_peer_ready(target_user=marie)
    after = OneTimePreKey.objects.filter(device=device, consumed_at__isnull=True).count()
    assert before == after == 2


# --- Delta AUTH-E : révocation ------------------------------------------------------


@pytest.mark.django_db
def test_kill_device_deletes_crypto_keys(api, jean):
    _jwt(api, jean)
    _publish_full_bundle(api)
    device = Device.objects.get(user=jean, device_uuid=DEVICE["device_uuid"])
    assert IdentityKey.objects.filter(device=device).exists()
    assert SignedPreKey.objects.filter(device=device).exists()
    assert OneTimePreKey.objects.filter(device=device).exists()

    revoke_device(user=jean, device_id=device.id)

    assert not IdentityKey.objects.filter(device=device).exists()
    assert not SignedPreKey.objects.filter(device=device).exists()
    assert not OneTimePreKey.objects.filter(device=device).exists()
    assert Device.objects.filter(pk=device.id).exists()


# --- Auth / portes -----------------------------------------------------------------


@pytest.mark.django_db
def test_without_jwt_401(api, db):
    r = api.get("/api/v1/crypto/me/one-time-prekeys/count")
    assert r.status_code == 401


@pytest.mark.django_db
def test_self_without_tos_403(api, user_role):
    fresh = User.objects.create_user(
        email="fresh.crypto@yas.tg", password=PASSWORD, username="fresh.crypto",
        role=user_role, first_name="Fresh", last_name="Crypto",
    )
    _jwt(api, fresh)
    r = api.get("/api/v1/crypto/me/one-time-prekeys/count")
    assert r.status_code == 403
    assert r.data["code"] == "TOS_REQUIRED"


@pytest.mark.django_db
def test_schema_has_crypto_paths(api, db):
    schema = api.get("/api/schema/")
    assert schema.status_code == 200
    text = schema.content.decode()
    assert "/api/v1/crypto/me/identity" in text
    assert "/bundles" in text
