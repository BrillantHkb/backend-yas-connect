import jwt
import pytest
from django.conf import settings
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.iam.helpers.mfa import login_until_jwt, post_mfa_verify
from apps.iam.models import Device, LoginHistory, RefreshToken, Role, Session, User
from apps.iam.services.token_service import hash_refresh_token

DEVICE = {"device_uuid": "test-web-1", "platform": "WEB"}
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)
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


def _login(api, **extra):
    body = {"password": PASSWORD, "device": DEVICE, **extra}
    return api.post("/api/v1/auth/login", body, format="json")


@pytest.mark.django_db
def test_login_email_ok(api, user_ok):
    r = _login(api, email="jean.dupont@yas.tg")
    assert r.status_code == 200
    challenge = r.data["data"]
    assert r.data["success"] is True
    assert challenge["mfa_required"] is True
    assert "access_token" not in challenge
    assert challenge["enroll"] is True
    v = post_mfa_verify(api, mfa_token=challenge["mfa_token"], user=user_ok)
    assert v.status_code == 200
    data = v.data["data"]
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "Bearer"
    assert data["user"]["email"] == "jean.dupont@yas.tg"
    assert "password" not in data["user"]
    assert data["user"]["role"]["code"] == "USER"
    assert data["user"]["status"] == "OFFLINE"
    assert "preferences" in data["user"]
    assert "privacy" in data["user"]
    payload = jwt.decode(
        data["access_token"],
        settings.JWT_TOKEN_SECRET,
        algorithms=[settings.YAS_JWT_ALGORITHM],
        issuer=settings.YAS_JWT_ISSUER,
    )
    session = Session.objects.get(user=user_ok, is_active=True)
    assert payload["jti"] == str(session.access_jti)
    assert payload["typ"] == "access"
    row = RefreshToken.objects.get(session=session)
    assert row.token_hash == hash_refresh_token(data["refresh_token"])
    assert row.token_hash != data["refresh_token"]
    user_ok.refresh_from_db()
    assert user_ok.last_login is not None
    assert user_ok.first_login is not None


@pytest.mark.django_db
def test_login_username_ok(api, user_ok):
    r = login_until_jwt(
        api, username="jean.dupont", password=PASSWORD, device=DEVICE
    )
    assert r.data["data"]["user"]["email"] == user_ok.email


@pytest.mark.django_db
def test_login_email_and_username_400(api, user_ok):
    r = _login(api, email="jean.dupont@yas.tg", username="jean.dupont")
    assert r.status_code == 400
    assert r.data["code"] == "VALIDATION_ERROR"


@pytest.mark.django_db
def test_pending_403(api, role):
    User.objects.create_user(
        email="pending@yas.tg",
        password=PASSWORD,
        username="pending",
        role=role,
        pending_approval=True,
    )
    r = _login(api, email="pending@yas.tg")
    assert r.status_code == 403
    assert r.data["code"] == "ACCOUNT_PENDING"


@pytest.mark.django_db
def test_disabled_403(api, role):
    User.objects.create_user(
        email="off@yas.tg",
        password=PASSWORD,
        username="offuser",
        role=role,
        is_active=False,
    )
    r = _login(api, email="off@yas.tg")
    assert r.status_code == 403
    assert r.data["code"] == "ACCOUNT_DISABLED"


@pytest.mark.django_db
def test_locked_403(api, role):
    User.objects.create_user(
        email="lock@yas.tg",
        password=PASSWORD,
        username="lockuser",
        role=role,
        is_locked=True,
    )
    r = _login(api, email="lock@yas.tg")
    assert r.status_code == 403
    assert r.data["code"] == "ACCOUNT_LOCKED"


@pytest.mark.django_db
def test_unknown_and_bad_password_same_401(api, user_ok):
    unknown = _login(api, email="inconnu@yas.tg")
    bad_pw = api.post(
        "/api/v1/auth/login",
        {"email": "jean.dupont@yas.tg", "password": "WrongPass1!", "device": DEVICE},
        format="json",
    )
    assert unknown.status_code == bad_pw.status_code == 401
    assert unknown.data["code"] == bad_pw.data["code"] == "INVALID_CREDENTIALS"
    assert unknown.data["message"] == bad_pw.data["message"] == MSG_INVALID


@pytest.mark.django_db
def test_unknown_username_401(api, user_ok):
    r = _login(api, username="inconnu")
    assert r.status_code == 401
    assert r.data["code"] == "INVALID_CREDENTIALS"
    assert r.data["message"] == MSG_INVALID


@pytest.mark.django_db
def test_rate_limit_sixth_attempt(api, user_ok):
    for _ in range(5):
        r = api.post(
            "/api/v1/auth/login",
            {"email": "jean.dupont@yas.tg", "password": "WrongPass1!", "device": DEVICE},
            format="json",
        )
        assert r.status_code == 401
    sixth = api.post(
        "/api/v1/auth/login",
        {"email": "jean.dupont@yas.tg", "password": "WrongPass1!", "device": DEVICE},
        format="json",
    )
    assert sixth.status_code == 401
    assert sixth.data["code"] == "INVALID_CREDENTIALS"
    assert LoginHistory.objects.filter(failure_reason="RATE_LIMITED").exists()


@pytest.mark.django_db
def test_history_and_ua(api, user_ok):
    challenge = _login(api, email="jean.dupont@yas.tg")
    assert LoginHistory.objects.filter(success=True).count() == 0
    post_mfa_verify(api, mfa_token=challenge.data["data"]["mfa_token"], user=user_ok)
    api.post(
        "/api/v1/auth/login",
        {"email": "jean.dupont@yas.tg", "password": "WrongPass1!", "device": DEVICE},
        format="json",
    )
    assert LoginHistory.objects.count() == 2
    success = LoginHistory.objects.get(success=True)
    assert success.browser == "Chrome"
    assert success.device_id is not None
    fail = LoginHistory.objects.get(success=False)
    assert fail.device_id is None


@pytest.mark.django_db
def test_last_login_only_on_success(api, user_ok):
    assert user_ok.last_login is None
    api.post(
        "/api/v1/auth/login",
        {"email": "jean.dupont@yas.tg", "password": "WrongPass1!", "device": DEVICE},
        format="json",
    )
    user_ok.refresh_from_db()
    assert user_ok.last_login is None
    challenge = _login(api, email="jean.dupont@yas.tg")
    user_ok.refresh_from_db()
    assert user_ok.last_login is None
    post_mfa_verify(api, mfa_token=challenge.data["data"]["mfa_token"], user=user_ok)
    user_ok.refresh_from_db()
    assert user_ok.last_login is not None


@pytest.mark.django_db
def test_refresh_rotates(api, user_ok):
    first = login_until_jwt(
        api, email="jean.dupont@yas.tg", password=PASSWORD, device=DEVICE
    )
    old = first.data["data"]["refresh_token"]
    r = api.post("/api/v1/auth/refresh", {"refresh_token": old}, format="json")
    assert r.status_code == 200
    assert r.data["data"]["refresh_token"] != old
    row = RefreshToken.objects.get(token_hash=hash_refresh_token(old))
    assert row.revoked_reason == "ROTATED"
    reuse = api.post("/api/v1/auth/refresh", {"refresh_token": old}, format="json")
    assert reuse.status_code == 401
    assert reuse.data["code"] == "FORCE_LOGOUT"
    assert Session.objects.filter(user=user_ok, is_active=True).count() == 0


@pytest.mark.django_db
def test_refresh_unknown_401(api, user_ok):
    r = api.post("/api/v1/auth/refresh", {"refresh_token": "not-a-real-token"}, format="json")
    assert r.status_code == 401
    assert r.data["code"] == "INVALID_REFRESH"


@pytest.mark.django_db
def test_second_login_same_device_upserts(api, user_ok):
    login_until_jwt(api, email="jean.dupont@yas.tg", password=PASSWORD, device=DEVICE)
    first_session = Session.objects.get(user=user_ok, is_active=True)
    login_until_jwt(api, email="jean.dupont@yas.tg", password=PASSWORD, device=DEVICE)
    assert Device.objects.filter(user=user_ok, device_uuid="test-web-1").count() == 1
    first_session.refresh_from_db()
    assert first_session.is_active is False
    assert first_session.revoke_reason == "NEW_LOGIN_SAME_DEVICE"
    current = Session.objects.get(user=user_ok, is_active=True)
    assert current.device_id is not None
    assert current.id != first_session.id


@pytest.mark.django_db
def test_health_still_public(api):
    r = api.get("/health")
    assert r.status_code == 200
    assert r.data["data"]["db"] is True
