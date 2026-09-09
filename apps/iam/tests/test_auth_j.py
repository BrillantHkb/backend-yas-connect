"""AUTH-J : lier un 2ᵉ appareil par QR + TOTP. Pas de JWT waiter avant confirm."""

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.iam.helpers.mfa import login_until_jwt, totp_now
from apps.iam.models import AuditLog, Device, LoginHistory, LoginMethod, Role, Session, User

PHONE = {"device_uuid": "phone-1", "platform": "ANDROID", "device_name": "Pixel"}
WAITER = {"device_uuid": "web-office-2", "platform": "WEB", "device_name": "Chrome bureau"}
UA = "Mozilla/5.0 pytest"
PASSWORD = "Secret123!"
MSG_INVALID = "Identifiant ou mot de passe incorrect."


@pytest.fixture
def api():
    cache.clear()
    client = APIClient()
    client.defaults["HTTP_USER_AGENT"] = UA
    return client


@pytest.fixture
def role(db):
    return Role.objects.create(code="USER", name="Utilisateur", is_system=True, level=0)


@pytest.fixture
def user_ok(role):
    return User.objects.create_user(
        email="jean.dupont@yas.tg",
        password=PASSWORD,
        username="jean.dupont",
        role=role,
        first_name="Jean",
        last_name="Dupont",
    )


@pytest.fixture
def other_user(role):
    return User.objects.create_user(
        email="marie@yas.tg",
        password=PASSWORD,
        username="marie.koevi",
        role=role,
    )


def _bearer(api, token):
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")


def _phone_jwt(api, user, device=PHONE):
    return login_until_jwt(api, email=user.email, password=PASSWORD, device=device)


def _start(api, device=WAITER):
    return api.post("/api/v1/auth/device-link/start", {"device": device}, format="json")


def _poll(api, challenge_id, secret):
    return api.get(
        f"/api/v1/auth/device-link/{challenge_id}",
        HTTP_X_DEVICE_LINK_SECRET=secret,
    )


def _confirm(api, token, challenge_id, otp=None, extra=None):
    _bearer(api, token)
    body = {"challenge_id": challenge_id}
    if otp is not None:
        body["otp"] = otp
    if extra:
        body.update(extra)
    return api.post("/api/v1/me/devices/link", body, format="json")


@pytest.mark.django_db
def test_start_secret_absent_from_qr(api, db):
    r = _start(api)
    assert r.status_code == 200, r.data
    data = r.data["data"]
    assert data["qr_payload"].startswith("yasconnect://device-link/v1?cid=")
    assert data["waiter_secret"] not in data["qr_payload"]
    assert data["expires_in"] == 120
    assert "access_token" not in data


@pytest.mark.django_db
def test_poll_without_or_wrong_secret(api, db):
    started = _start(api).data["data"]
    cid = started["challenge_id"]
    missing = api.get(f"/api/v1/auth/device-link/{cid}")
    assert missing.status_code == 403
    assert missing.data["code"] == "DEVICE_LINK_FORBIDDEN"
    bad = _poll(api, cid, "not-the-secret")
    assert bad.status_code == 403
    assert bad.data["code"] == "DEVICE_LINK_FORBIDDEN"


@pytest.mark.django_db
def test_poll_pending_no_jwt(api, db):
    started = _start(api).data["data"]
    r = _poll(api, started["challenge_id"], started["waiter_secret"])
    assert r.status_code == 200
    assert r.data["data"]["status"] == "PENDING"
    assert "access_token" not in r.data["data"]
    assert r.data["data"]["expires_in"] <= 120


@pytest.mark.django_db
def test_confirm_without_otp(api, user_ok):
    tok = _phone_jwt(api, user_ok).data["data"]["access_token"]
    cid = _start(api).data["data"]["challenge_id"]
    r = _confirm(api, tok, cid)
    assert r.status_code == 400


@pytest.mark.django_db
def test_confirm_backup_forbidden(api, user_ok):
    enrolled = _phone_jwt(api, user_ok)
    tok = enrolled.data["data"]["access_token"]
    backup = enrolled.data["data"]["backup_codes"][0]
    cid = _start(api).data["data"]["challenge_id"]
    r = _confirm(api, tok, cid, extra={"backup_code": backup})
    assert r.status_code == 400
    assert r.data["code"] == "MFA_BACKUP_NOT_ALLOWED"


@pytest.mark.django_db
def test_totp_false_waiter_still_pending(api, user_ok):
    tok = _phone_jwt(api, user_ok).data["data"]["access_token"]
    started = _start(api).data["data"]
    r = _confirm(api, tok, started["challenge_id"], otp="000000")
    assert r.status_code == 401
    assert r.data["code"] == "INVALID_CREDENTIALS"
    assert r.data["message"] == MSG_INVALID
    poll = _poll(api, started["challenge_id"], started["waiter_secret"])
    assert poll.data["data"]["status"] == "PENDING"
    assert "access_token" not in poll.data["data"]


@pytest.mark.django_db
def test_totp_ok_tokens_one_shot(api, user_ok):
    tok = _phone_jwt(api, user_ok).data["data"]["access_token"]
    started = _start(api).data["data"]
    r = _confirm(api, tok, started["challenge_id"], otp=totp_now(user_ok))
    assert r.status_code == 200, r.data
    assert r.data["data"]["linked"] is True
    assert "access_token" not in r.data["data"]
    first = _poll(api, started["challenge_id"], started["waiter_secret"])
    assert first.status_code == 200
    assert first.data["data"]["status"] == "APPROVED"
    assert first.data["data"]["access_token"]
    assert first.data["data"]["refresh_token"]
    second = _poll(api, started["challenge_id"], started["waiter_secret"])
    assert second.status_code == 410
    assert second.data["code"] == "DEVICE_LINK_EXPIRED"


@pytest.mark.django_db
def test_ttl_expired_both_sides(api, user_ok):
    tok = _phone_jwt(api, user_ok).data["data"]["access_token"]
    started = _start(api).data["data"]
    cache.clear()  # simule TTL écoulé (LocMem)
    poll = _poll(api, started["challenge_id"], started["waiter_secret"])
    assert poll.status_code == 410
    confirm = _confirm(api, tok, started["challenge_id"], otp=totp_now(user_ok))
    assert confirm.status_code == 410
    assert confirm.data["code"] == "DEVICE_LINK_EXPIRED"


@pytest.mark.django_db
def test_link_self_same_uuid(api, user_ok):
    tok = _phone_jwt(api, user_ok).data["data"]["access_token"]
    started = _start(api, device=PHONE).data["data"]
    r = _confirm(api, tok, started["challenge_id"], otp=totp_now(user_ok))
    assert r.status_code == 400
    assert r.data["code"] == "DEVICE_LINK_SELF"


@pytest.mark.django_db
def test_uuid_taken_other_user(api, user_ok, other_user):
    login_until_jwt(api, email=other_user.email, password=PASSWORD, device=WAITER)
    tok = _phone_jwt(api, user_ok).data["data"]["access_token"]
    started = _start(api, device=WAITER).data["data"]
    r = _confirm(api, tok, started["challenge_id"], otp=totp_now(user_ok))
    assert r.status_code == 409
    assert r.data["code"] == "DEVICE_UUID_TAKEN"


@pytest.mark.django_db
def test_first_uuid_via_qr_suspicious(api, user_ok):
    tok = _phone_jwt(api, user_ok).data["data"]["access_token"]
    started = _start(api).data["data"]
    r = _confirm(api, tok, started["challenge_id"], otp=totp_now(user_ok))
    assert r.status_code == 200
    device = Device.objects.get(user=user_ok, device_uuid=WAITER["device_uuid"])
    hist = LoginHistory.objects.filter(user=user_ok, device=device, success=True).latest(
        "created_at"
    )
    assert hist.suspicious is True
    assert hist.login_method == LoginMethod.DEVICE_LINK
    assert AuditLog.objects.filter(action="DEVICE_NEW", entity_id=device.id).exists()
    assert AuditLog.objects.filter(action="DEVICE_LINK", entity_id=device.id).exists()


@pytest.mark.django_db
def test_trusted_phone_still_requires_totp(api, user_ok):
    tok = _phone_jwt(api, user_ok).data["data"]["access_token"]
    phone = Device.objects.get(user=user_ok, device_uuid=PHONE["device_uuid"])
    _bearer(api, tok)
    patched = api.patch(f"/api/v1/me/devices/{phone.id}", {"trusted": True}, format="json")
    assert patched.status_code == 200
    started = _start(api).data["data"]
    missing = _confirm(api, tok, started["challenge_id"])
    assert missing.status_code == 400
    ok = _confirm(api, tok, started["challenge_id"], otp=totp_now(user_ok))
    assert ok.status_code == 200


@pytest.mark.django_db
def test_waiter_session_login_method(api, user_ok):
    tok = _phone_jwt(api, user_ok).data["data"]["access_token"]
    started = _start(api).data["data"]
    _confirm(api, tok, started["challenge_id"], otp=totp_now(user_ok))
    tokens = _poll(api, started["challenge_id"], started["waiter_secret"]).data["data"]
    session = Session.objects.get(user=user_ok, device__device_uuid=WAITER["device_uuid"])
    assert session.login_method == LoginMethod.DEVICE_LINK
    assert session.is_active is True
    assert tokens["access_token"]


@pytest.mark.django_db
def test_enroll_auth_c_unchanged(api, user_ok):
    r = api.post(
        "/api/v1/auth/login",
        {"email": user_ok.email, "password": PASSWORD, "device": PHONE},
        format="json",
    )
    assert r.status_code == 200
    data = r.data["data"]
    assert data["mfa_required"] is True
    assert data["enroll"] is True
    assert data["otpauth_uri"].startswith("otpauth://")
    assert "device-link" not in data["otpauth_uri"]
    assert "access_token" not in data


@pytest.mark.django_db
def test_health_and_docs(api, db):
    assert api.get("/health").status_code == 200
    assert api.get("/api/docs/").status_code == 200
    schema = api.get("/api/schema/").content.decode()
    assert "/api/v1/auth/device-link/start" in schema
    assert "/api/v1/me/devices/link" in schema
