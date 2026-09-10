"""AUTH-G : changement MDP JWT + oubli via Authenticator (pas de mail)."""

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.iam.helpers.compliance import close_gates
from apps.iam.helpers.mfa import login_until_jwt, totp_now
from apps.iam.models import (
    AuditLog,
    PasswordHistory,
    PasswordResetToken,
    ResetChannel,
    Role,
    Session,
    User,
)
from apps.iam.services.mfa_service import hash_backup_code
from apps.iam.services.password_service import MSG_FORGOT, verify_password

DEVICE = {"device_uuid": "test-web-1", "platform": "WEB"}
DEVICE2 = {"device_uuid": "test-web-2", "platform": "WEB"}
UA = "Mozilla/5.0 pytest"
PASSWORD = "Secret123!"
NEW_PASSWORD = "SecretApp456!"
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
    return close_gates(
        User.objects.create_user(
            email="jean.dupont@yas.tg",
            password=PASSWORD,
            username="jean.dupont",
            role=role,
            first_name="Jean",
            last_name="Dupont",
        )
    )


@pytest.fixture
def user_fresh(role):
    return User.objects.create_user(
        email="neuf@yas.tg",
        password=PASSWORD,
        username="user.neuf",
        role=role,
    )


def _body(r):
    data = getattr(r, "data", None)
    if isinstance(data, dict):
        return data
    return r.json()


def _jwt(api, user, device=DEVICE, password=PASSWORD):
    r = login_until_jwt(api, email=user.email, password=password, device=device)
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {r.data['data']['access_token']}")
    return r


def _login(api, email, password, device=DEVICE):
    return api.post(
        "/api/v1/auth/login",
        {"email": email, "password": password, "device": device},
        format="json",
    )


@pytest.mark.django_db
def test_change_ok_archives_history(api, user_ok):
    _jwt(api, user_ok)
    r = api.post(
        "/api/v1/me/password",
        {"old_password": PASSWORD, "new_password": NEW_PASSWORD},
        format="json",
    )
    assert r.status_code == 200
    assert r.data["success"] is True
    user_ok.refresh_from_db()
    assert verify_password(NEW_PASSWORD, user_ok.password)
    assert PasswordHistory.objects.filter(user=user_ok).count() == 1
    api.credentials()
    old = _login(api, user_ok.email, PASSWORD)
    assert old.status_code == 401
    assert old.data["code"] == "INVALID_CREDENTIALS"
    assert old.data["message"] == MSG_INVALID


@pytest.mark.django_db
def test_change_bad_old_password(api, user_ok):
    _jwt(api, user_ok)
    r = api.post(
        "/api/v1/me/password",
        {"old_password": "WrongPass1!", "new_password": NEW_PASSWORD},
        format="json",
    )
    assert r.status_code == 400
    assert r.data["code"] == "INVALID_OLD_PASSWORD"


@pytest.mark.django_db
def test_change_same_password(api, user_ok):
    _jwt(api, user_ok)
    r = api.post(
        "/api/v1/me/password",
        {"old_password": PASSWORD, "new_password": PASSWORD},
        format="json",
    )
    assert r.status_code == 400
    assert r.data["code"] == "SAME_PASSWORD"


@pytest.mark.django_db
def test_change_weak_password(api, user_ok):
    _jwt(api, user_ok)
    r = api.post(
        "/api/v1/me/password",
        {"old_password": PASSWORD, "new_password": "short"},
        format="json",
    )
    assert r.status_code == 400
    assert r.data["code"] == "WEAK_PASSWORD"


@pytest.mark.django_db
def test_change_reused_history(api, user_ok):
    _jwt(api, user_ok)
    ok = api.post(
        "/api/v1/me/password",
        {"old_password": PASSWORD, "new_password": NEW_PASSWORD},
        format="json",
    )
    assert ok.status_code == 200
    reused = api.post(
        "/api/v1/me/password",
        {"old_password": NEW_PASSWORD, "new_password": PASSWORD},
        format="json",
    )
    assert reused.status_code == 400
    assert reused.data["code"] == "PASSWORD_REUSED"


@pytest.mark.django_db
def test_change_logout_others(api, user_ok):
    first = _jwt(api, user_ok, device=DEVICE)
    first_session = Session.objects.get(user=user_ok, is_active=True)
    api.credentials()
    second = _jwt(api, user_ok, device=DEVICE2)
    r = api.post(
        "/api/v1/me/password",
        {"old_password": PASSWORD, "new_password": NEW_PASSWORD},
        format="json",
    )
    assert r.status_code == 200
    first_session.refresh_from_db()
    assert first_session.is_active is False
    assert first_session.revoke_reason == "PASSWORD_CHANGE"
    current = Session.objects.get(user=user_ok, is_active=True)
    assert current.access_jti is not None
    assert str(current.access_jti) != str(first_session.access_jti)
    assert first.data["data"]["access_token"] != second.data["data"]["access_token"]


@pytest.mark.django_db
def test_change_without_jwt(api, user_ok):
    r = api.post(
        "/api/v1/me/password",
        {"old_password": PASSWORD, "new_password": NEW_PASSWORD},
        format="json",
    )
    # CSRF Django sur POST sans session : 403 ; DRF NotAuthenticated : 401
    assert r.status_code in (401, 403)
    assert _body(r).get("code") != "TOS_REQUIRED"


@pytest.mark.django_db
def test_change_tos_required(api, user_fresh):
    _jwt(api, user_fresh)
    r = api.post(
        "/api/v1/me/password",
        {"old_password": PASSWORD, "new_password": NEW_PASSWORD},
        format="json",
    )
    assert r.status_code == 403
    assert _body(r)["code"] == "TOS_REQUIRED"


@pytest.mark.django_db
def test_forgot_unknown_email(api, db):
    r = api.post(
        "/api/v1/auth/password/forgot",
        {"email": "inconnu@yas.tg"},
        format="json",
    )
    assert r.status_code == 200
    assert r.data["message"] == MSG_FORGOT
    assert PasswordResetToken.objects.count() == 0


@pytest.mark.django_db
def test_forgot_known_no_mail(api, user_ok):
    r = api.post(
        "/api/v1/auth/password/forgot",
        {"email": user_ok.email},
        format="json",
    )
    assert r.status_code == 200
    assert r.data["message"] == MSG_FORGOT
    assert PasswordResetToken.objects.count() == 0
    assert AuditLog.objects.filter(action="PASSWORD_FORGOT", user=user_ok).exists()


@pytest.mark.django_db
def test_verify_totp_issues_ticket(api, user_ok):
    _jwt(api, user_ok)
    api.credentials()
    r = api.post(
        "/api/v1/auth/password/reset/verify",
        {"email": user_ok.email, "otp": totp_now(user_ok)},
        format="json",
    )
    assert r.status_code == 200
    token = r.data["data"]["reset_token"]
    assert token
    assert r.data["data"]["expires_in"] == 600
    row = PasswordResetToken.objects.get(user=user_ok)
    assert row.reset_channel == ResetChannel.TOTP
    assert row.used_at is None
    assert row.revoked_at is None


@pytest.mark.django_db
def test_verify_rejects_channel(api, user_ok):
    r = api.post(
        "/api/v1/auth/password/reset/verify",
        {"email": user_ok.email, "otp": "123456", "channel": "EMAIL"},
        format="json",
    )
    assert r.status_code == 400
    assert r.data["code"] == "VALIDATION_ERROR"


@pytest.mark.django_db
def test_verify_without_enroll(api, user_fresh):
    r = api.post(
        "/api/v1/auth/password/reset/verify",
        {"email": user_fresh.email, "otp": "123456"},
        format="json",
    )
    assert r.status_code == 400
    assert r.data["code"] == "MFA_INVALID"


@pytest.mark.django_db
def test_second_verify_revokes_old_ticket(api, user_ok):
    _jwt(api, user_ok)
    api.credentials()
    first = api.post(
        "/api/v1/auth/password/reset/verify",
        {"email": user_ok.email, "otp": totp_now(user_ok)},
        format="json",
    )
    second = api.post(
        "/api/v1/auth/password/reset/verify",
        {"email": user_ok.email, "otp": totp_now(user_ok)},
        format="json",
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.data["data"]["reset_token"] != second.data["data"]["reset_token"]
    old = PasswordResetToken.objects.get(
        user=user_ok, revoked_at__isnull=False
    )
    assert old.used_at is None
    live = PasswordResetToken.objects.get(user=user_ok, revoked_at__isnull=True)
    assert live.used_at is None


@pytest.mark.django_db
def test_reset_ok_then_replay(api, user_ok):
    _jwt(api, user_ok)
    api.credentials()
    ticket = api.post(
        "/api/v1/auth/password/reset/verify",
        {"email": user_ok.email, "otp": totp_now(user_ok)},
        format="json",
    ).data["data"]["reset_token"]
    ok = api.post(
        "/api/v1/auth/password/reset",
        {"reset_token": ticket, "new_password": NEW_PASSWORD},
        format="json",
    )
    assert ok.status_code == 200
    user_ok.refresh_from_db()
    assert verify_password(NEW_PASSWORD, user_ok.password)
    row = PasswordResetToken.objects.get(user=user_ok)
    assert row.used_at is not None
    replay = api.post(
        "/api/v1/auth/password/reset",
        {"reset_token": ticket, "new_password": "AutrePass789!"},
        format="json",
    )
    assert replay.status_code == 400
    assert replay.data["code"] == "INVALID_TOKEN"


@pytest.mark.django_db
def test_reset_logout_all_default(api, user_ok):
    _jwt(api, user_ok)
    assert Session.objects.filter(user=user_ok, is_active=True).count() == 1
    api.credentials()
    ticket = api.post(
        "/api/v1/auth/password/reset/verify",
        {"email": user_ok.email, "otp": totp_now(user_ok)},
        format="json",
    ).data["data"]["reset_token"]
    api.post(
        "/api/v1/auth/password/reset",
        {"reset_token": ticket, "new_password": NEW_PASSWORD},
        format="json",
    )
    assert Session.objects.filter(user=user_ok, is_active=True).count() == 0
    killed = Session.objects.get(user=user_ok)
    assert killed.revoke_reason == "PASSWORD_RESET"


@pytest.mark.django_db
def test_reset_with_backup_code(api, user_ok):
    enrolled = _jwt(api, user_ok)
    backup = enrolled.data["data"]["backup_codes"][0]
    api.credentials()
    ticket = api.post(
        "/api/v1/auth/password/reset/verify",
        {"email": user_ok.email, "backup_code": backup},
        format="json",
    )
    assert ticket.status_code == 200
    api.post(
        "/api/v1/auth/password/reset",
        {
            "reset_token": ticket.data["data"]["reset_token"],
            "new_password": NEW_PASSWORD,
        },
        format="json",
    )
    user_ok.refresh_from_db()
    assert hash_backup_code(backup) not in user_ok.otp_secret.backup_codes
    assert verify_password(NEW_PASSWORD, user_ok.password)


@pytest.mark.django_db
def test_change_ldap_user_app_hash_only(api, role):
    user = close_gates(
        User.objects.create_user(
            email="lucie.ad@yas.tg",
            password=PASSWORD,
            username="lucie.ad",
            role=role,
            ldap_dn="CN=Lucie Ad,OU=Users,DC=yas,DC=tg",
        )
    )
    _jwt(api, user)
    r = api.post(
        "/api/v1/me/password",
        {"old_password": PASSWORD, "new_password": NEW_PASSWORD},
        format="json",
    )
    assert r.status_code == 200
    user.refresh_from_db()
    assert user.ldap_dn.startswith("CN=")
    assert verify_password(NEW_PASSWORD, user.password)


@pytest.mark.django_db
def test_pending_locked_disabled(api, role):
    pending = User.objects.create_user(
        email="pending@yas.tg",
        password=PASSWORD,
        username="pending.user",
        role=role,
        pending_approval=True,
    )
    locked = User.objects.create_user(
        email="locked@yas.tg",
        password=PASSWORD,
        username="locked.user",
        role=role,
        is_locked=True,
    )
    disabled = User.objects.create_user(
        email="off@yas.tg",
        password=PASSWORD,
        username="off.user",
        role=role,
        is_active=False,
    )
    for email in (pending.email, locked.email, disabled.email):
        forgot = api.post("/api/v1/auth/password/forgot", {"email": email}, format="json")
        assert forgot.status_code == 200
        verify = api.post(
            "/api/v1/auth/password/reset/verify",
            {"email": email, "otp": "123456"},
            format="json",
        )
        assert verify.status_code == 400
        assert verify.data["code"] == "MFA_INVALID"
    assert PasswordResetToken.objects.count() == 0


@pytest.mark.django_db
def test_forgot_rate_limit_stays_200(api, user_ok):
    for _ in range(3):
        r = api.post(
            "/api/v1/auth/password/forgot",
            {"email": user_ok.email},
            format="json",
        )
        assert r.status_code == 200
    fourth = api.post(
        "/api/v1/auth/password/forgot",
        {"email": user_ok.email},
        format="json",
    )
    assert fourth.status_code == 200
    assert fourth.data["message"] == MSG_FORGOT
    assert AuditLog.objects.filter(action="PASSWORD_FORGOT_RATE_LIMITED").exists()


@pytest.mark.django_db
def test_health_and_docs(api, db):
    assert api.get("/health").status_code == 200
    assert api.get("/api/docs/").status_code == 200
    schema = api.get("/api/schema/").content.decode()
    assert "/api/v1/me/password" in schema
    assert "/api/v1/auth/password/forgot" in schema
    assert "/api/v1/auth/password/reset/verify" in schema
    assert "/api/v1/auth/password/reset" in schema
