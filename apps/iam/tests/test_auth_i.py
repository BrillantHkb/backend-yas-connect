"""AUTH-I : historique de connexions, lock auto, change email, unlock admin."""

import json
from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APIClient

from apps.iam.helpers.compliance import close_gates
from apps.iam.helpers.mfa import login_until_jwt, post_mfa_verify
from apps.iam.jobs import unlock_expired_locks
from apps.iam.models import AuditLog, EmailVerification, LoginHistory, Role, User
from apps.iam.services.ldap_service import LdapBindFailed
from apps.iam.services.lock_service import mark_suspicious

DEVICE = {"device_uuid": "test-web-1", "platform": "WEB", "device_name": "PC lab"}
UA = "Mozilla/5.0 pytest"
PASSWORD = "Secret123!"
WRONG = "WrongPass1!"
ADMIN_PASSWORD = "Admin123!"
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
def admin_role(db):
    return Role.objects.create(code="ADMIN", name="Administrateur", is_system=True, level=100)


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
def admin_ok(admin_role):
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


@pytest.fixture
def user_fresh(role):
    return User.objects.create_user(
        email="neuf@yas.tg",
        password=PASSWORD,
        username="user.neuf",
        role=role,
    )


def _jwt(api, user, device=DEVICE, password=PASSWORD):
    r = login_until_jwt(api, email=user.email, password=password, device=device)
    token = r.data["data"]["access_token"]
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return r


def _bad_login(api, email, password=WRONG, device=DEVICE):
    return api.post(
        "/api/v1/auth/login",
        {"email": email, "password": password, "device": device},
        format="json",
    )


def _lock_with_failures(api, email, n=5):
    last = None
    for _ in range(n):
        last = _bad_login(api, email)
        assert last.status_code == 401
        assert last.data["code"] == "INVALID_CREDENTIALS"
    return last


@pytest.mark.django_db
def test_me_security_logins_success_and_failures(api, user_ok):
    _bad_login(api, user_ok.email)
    _jwt(api, user_ok)
    r = api.get("/api/v1/me/security/logins")
    assert r.status_code == 200
    logins = r.data["data"]["logins"]
    assert any(row["success"] is True for row in logins)
    assert any(row["success"] is False for row in logins)
    blob = str(r.data)
    assert "token_hash" not in blob
    assert "password_hash" not in blob
    first = logins[0]
    for key in (
        "id",
        "created_at",
        "success",
        "suspicious",
        "ip_address",
        "country",
        "city",
        "device_id",
        "device_name",
        "platform",
        "browser",
        "login_method",
        "failure_reason",
    ):
        assert key in first


@pytest.mark.django_db
def test_me_security_logins_geo_null(api, user_ok):
    _jwt(api, user_ok)
    r = api.get("/api/v1/me/security/logins")
    assert r.status_code == 200
    successes = [row for row in r.data["data"]["logins"] if row["success"]]
    assert successes
    assert successes[0]["country"] is None


@pytest.mark.django_db
def test_first_uuid_suspicious(api, user_ok):
    _jwt(api, user_ok)
    r = api.get("/api/v1/me/security/logins")
    success = next(row for row in r.data["data"]["logins"] if row["success"])
    assert success["suspicious"] is True


@pytest.mark.django_db
def test_new_country_suspicious_login_ok(api, user_ok):
    _jwt(api, user_ok)
    h1 = LoginHistory.objects.filter(user=user_ok, success=True).order_by("created_at").last()
    h1.country = "TG"
    h1.save(update_fields=["country"])
    mark_suspicious(history=h1)
    assert not AuditLog.objects.filter(action="LOGIN_NEW_COUNTRY").exists()

    api.credentials()
    r = login_until_jwt(api, email=user_ok.email, password=PASSWORD, device=DEVICE)
    assert r.status_code == 200
    h2 = LoginHistory.objects.filter(user=user_ok, success=True).order_by("created_at").last()
    assert h2.id != h1.id
    h2.country = "FR"
    h2.save(update_fields=["country"])
    mark_suspicious(history=h2)
    h2.refresh_from_db()
    assert h2.suspicious is True
    assert AuditLog.objects.filter(action="LOGIN_NEW_COUNTRY").exists()


@pytest.mark.django_db
def test_first_geo_no_country_alert(api, user_ok):
    _jwt(api, user_ok)
    h1 = LoginHistory.objects.filter(user=user_ok, success=True).order_by("created_at").last()
    h1.country = "TG"
    h1.save(update_fields=["country"])
    mark_suspicious(history=h1)
    assert not AuditLog.objects.filter(action="LOGIN_NEW_COUNTRY").exists()


@pytest.mark.django_db
def test_fifth_bad_password_locks_still_401(api, user_ok):
    last = _lock_with_failures(api, user_ok.email, n=5)
    assert last.status_code == 401
    assert last.data["code"] == "INVALID_CREDENTIALS"
    assert last.data["message"] == MSG_INVALID
    user_ok.refresh_from_db()
    assert user_ok.is_locked is True
    assert user_ok.locked_at is not None
    assert AuditLog.objects.filter(action="ACCOUNT_LOCK", entity_id=user_ok.id).exists()


@pytest.mark.django_db
def test_good_password_while_locked_403(api, user_ok):
    _lock_with_failures(api, user_ok.email)
    r = api.post(
        "/api/v1/auth/login",
        {"email": user_ok.email, "password": PASSWORD, "device": DEVICE},
        format="json",
    )
    assert r.status_code == 403
    assert r.data["code"] == "ACCOUNT_LOCKED"


@pytest.mark.django_db
def test_mfa_invalid_does_not_lock(api, user_ok):
    login_until_jwt(api, email=user_ok.email, password=PASSWORD, device=DEVICE)
    cache.clear()  # throttle MFA IP du enroll : 5 OTP faux doivent tous être MFA_INVALID
    for _ in range(5):
        challenge = api.post(
            "/api/v1/auth/login",
            {"email": user_ok.email, "password": PASSWORD, "device": DEVICE},
            format="json",
        )
        assert challenge.status_code == 200
        v = post_mfa_verify(
            api,
            mfa_token=challenge.data["data"]["mfa_token"],
            user=user_ok,
            otp="000000",
        )
        assert v.status_code == 401
    user_ok.refresh_from_db()
    assert user_ok.is_locked is False
    assert LoginHistory.objects.filter(user=user_ok, failure_reason="MFA_INVALID").count() >= 5


@pytest.mark.django_db
def test_unknown_email_never_locks(api, user_ok):
    for _ in range(20):
        r = _bad_login(api, "inconnu@yas.tg")
        assert r.status_code == 401
        assert r.data["code"] == "INVALID_CREDENTIALS"
    user_ok.refresh_from_db()
    assert user_ok.is_locked is False
    assert not User.objects.filter(is_locked=True).exists()


@pytest.mark.django_db
def test_admin_unlock_then_login_totp(api, user_ok, admin_ok):
    _lock_with_failures(api, user_ok.email)
    user_ok.refresh_from_db()
    assert user_ok.is_locked is True
    _jwt(api, admin_ok, password=ADMIN_PASSWORD)
    r = api.post(f"/api/v1/admin/users/{user_ok.id}/unlock")
    assert r.status_code == 200
    user_ok.refresh_from_db()
    assert user_ok.is_locked is False
    assert user_ok.locked_at is None
    assert AuditLog.objects.filter(action="ACCOUNT_UNLOCK", entity_id=user_ok.id).exists()
    api.credentials()
    ok = login_until_jwt(api, email=user_ok.email, password=PASSWORD, device=DEVICE)
    assert ok.status_code == 200
    assert "access_token" in ok.data["data"]


@pytest.mark.django_db
def test_lazy_unlock_after_ttl(api, user_ok):
    user_ok.is_locked = True
    user_ok.locked_at = timezone.now() - timedelta(seconds=1801)
    user_ok.save(update_fields=["is_locked", "locked_at", "updated_at"])
    r = login_until_jwt(api, email=user_ok.email, password=PASSWORD, device=DEVICE)
    assert r.status_code == 200
    user_ok.refresh_from_db()
    assert user_ok.is_locked is False
    assert user_ok.locked_at is None


@pytest.mark.django_db
def test_unlock_expired_locks_job(api, user_ok):
    user_ok.is_locked = True
    user_ok.locked_at = timezone.now() - timedelta(seconds=1801)
    user_ok.save(update_fields=["is_locked", "locked_at", "updated_at"])
    n = unlock_expired_locks()
    assert n == 1
    user_ok.refresh_from_db()
    assert user_ok.is_locked is False
    assert user_ok.locked_at is None
    assert AuditLog.objects.filter(action="ACCOUNT_UNLOCK_AUTO", entity_id=user_ok.id).exists()


@pytest.mark.django_db
def test_email_change_202_then_verify(api, user_ok):
    _jwt(api, user_ok)
    old = user_ok.email
    token = "email-change-token-lab"
    with patch(
        "apps.iam.services.email_verification_service.secrets.token_urlsafe",
        return_value=token,
    ):
        r = api.post("/api/v1/me/email", {"email": "jean.dupont2@yas.tg"}, format="json")
    assert r.status_code == 202
    user_ok.refresh_from_db()
    assert user_ok.email == old
    row = EmailVerification.objects.get(purpose=EmailVerification.Purpose.EMAIL_CHANGE)
    assert row.email == "jean.dupont2@yas.tg"
    api.credentials()
    v = api.post("/api/v1/auth/email/verify", {"token": token}, format="json")
    assert v.status_code == 200
    user_ok.refresh_from_db()
    assert user_ok.email == "jean.dupont2@yas.tg"
    replay = api.post("/api/v1/auth/email/verify", {"token": token}, format="json")
    assert replay.status_code == 200
    ok = login_until_jwt(api, email="jean.dupont2@yas.tg", password=PASSWORD, device=DEVICE)
    assert ok.status_code == 200


@pytest.mark.django_db
def test_email_change_forbidden_ldap(api, user_ok):
    user_ok.ldap_dn = "CN=Jean Dupont,OU=Users,DC=yas,DC=tg"
    user_ok.save(update_fields=["ldap_dn", "updated_at"])
    _jwt(api, user_ok)
    r = api.post("/api/v1/me/email", {"email": "alias@yas.tg"}, format="json")
    assert r.status_code == 400
    assert r.data["code"] == "EMAIL_CHANGE_FORBIDDEN"


@pytest.mark.django_db
def test_email_resend_fourth_429(api, user_ok):
    _jwt(api, user_ok)
    r = api.post("/api/v1/me/email", {"email": "jean.nouveau@yas.tg"}, format="json")
    assert r.status_code == 202
    for _ in range(3):
        ok = api.post("/api/v1/me/email/resend", format="json")
        assert ok.status_code == 200
    limited = api.post("/api/v1/me/email/resend", format="json")
    assert limited.status_code == 429
    assert limited.data["code"] == "EMAIL_RESEND_RATE_LIMITED"


@pytest.mark.django_db
def test_register_resend_unknown_200(api):
    before = EmailVerification.objects.count()
    r = api.post(
        "/api/v1/auth/register/resend-verification",
        {"email": "inconnu@yas.tg"},
        format="json",
    )
    assert r.status_code == 200
    assert EmailVerification.objects.count() == before


@pytest.mark.django_db
def test_ldap_bind_fail_five_locks_yas(api, user_ok):
    user_ok.ldap_dn = "CN=Jean Dupont,OU=Users,DC=yas,DC=tg"
    user_ok.save(update_fields=["ldap_dn", "updated_at"])
    with (
        patch("apps.iam.services.ldap_service.bind_user_dn", side_effect=LdapBindFailed()),
        patch("apps.iam.services.ldap_service.search_user_dn", side_effect=LdapBindFailed()),
    ):
        for _ in range(5):
            r = api.post(
                "/api/v1/auth/login/ldap",
                {"email": user_ok.email, "password": "bad", "device": DEVICE},
                format="json",
            )
            assert r.status_code == 401
            assert r.data["code"] == "INVALID_CREDENTIALS"
    user_ok.refresh_from_db()
    assert user_ok.is_locked is True
    assert user_ok.ldap_dn == "CN=Jean Dupont,OU=Users,DC=yas,DC=tg"


@pytest.mark.django_db
def test_new_user_logins_tos_required(api, user_fresh):
    r = login_until_jwt(api, email=user_fresh.email, password=PASSWORD, device=DEVICE)
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {r.data['data']['access_token']}")
    denied = api.get("/api/v1/me/security/logins")
    assert denied.status_code == 403
    body = json.loads(denied.content)
    assert body["code"] == "TOS_REQUIRED"


@pytest.mark.django_db
def test_admin_logins_404_unknown(api, admin_ok):
    _jwt(api, admin_ok, password=ADMIN_PASSWORD)
    r = api.get(f"/api/v1/admin/users/{uuid4()}/logins")
    assert r.status_code == 404
    assert r.data["code"] == "NOT_FOUND"


@pytest.mark.django_db
def test_health_and_docs_schema(api, db):
    assert api.get("/health").status_code == 200
    assert api.get("/api/docs/").status_code == 200
    schema = api.get("/api/schema/").content.decode()
    assert "/api/v1/me/security/logins" in schema
    assert "/api/v1/admin/users/{id}/unlock" in schema or "/unlock" in schema
    assert "/api/v1/auth/email/verify" in schema
