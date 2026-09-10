"""AUTH-C : MFA TOTP obligatoire après facteur 1. LDAP mocké."""

from unittest.mock import patch

import pyotp
import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.annuaire.models import Segment, SegmentType
from apps.iam.helpers.compliance import close_gates
from apps.iam.helpers.mfa import login_until_jwt, post_mfa_verify, totp_now
from apps.iam.models import AuditLog, Device, LoginHistory, OtpSecret, Region, Role, Session, User
from apps.iam.services.ldap_service import AdIdentity
from apps.iam.services.mfa_service import decrypt_totp_secret, hash_backup_code

DEVICE = {"device_uuid": "test-web-1", "platform": "WEB"}
UA = "Mozilla/5.0 pytest"
PASSWORD = "Secret123!"
ADMIN_PASSWORD = "Admin123!"
APP_PASSWORD = "SecretApp123!"
AD_PASSWORD = "WindowsPass1!"
MSG_INVALID = "Identifiant ou mot de passe incorrect."
IDENTITY = AdIdentity(
    dn="CN=Lucie Ad,OU=Users,DC=yas,DC=tg",
    upn="lucie.ad@yas.tg",
    sam="lucie.ad",
)


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
def region(db):
    return Region.objects.create(code="MARITIME", name="Maritime")


@pytest.fixture
def segment(db):
    st = SegmentType.objects.create(code="DIRECTION", name="Direction", level=0)
    return Segment.objects.create(code="YAS", name="YAS Togo", segment_type=st, is_active=True)


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


def _login(api, **extra):
    body = {"password": PASSWORD, "device": DEVICE, **extra}
    return api.post("/api/v1/auth/login", body, format="json")


def _register_ad(api, region, segment):
    with (
        patch("apps.iam.services.register_service.search_user_identity", return_value=IDENTITY),
        patch("apps.iam.services.register_service.bind_user_dn"),
    ):
        return api.post(
            "/api/v1/auth/register/ad",
            {
                "email": "lucie.ad@yas.tg",
                "password_ad": AD_PASSWORD,
                "password": APP_PASSWORD,
                "device": DEVICE,
                "first_name": "Lucie",
                "last_name": "Ad",
                "phone": "+22890123456",
                "job_title": "NOC",
                "region_id": str(region.id),
                "segment_id": str(segment.id),
            },
            format="json",
        )


@pytest.mark.django_db
def test_login_mfa_required_no_jwt(api, user_ok):
    r = _login(api, email="jean.dupont@yas.tg")
    assert r.status_code == 200
    data = r.data["data"]
    assert data["mfa_required"] is True
    assert "access_token" not in data
    assert "refresh_token" not in data
    assert data["enroll"] is True
    assert data["otpauth_uri"].startswith("otpauth://totp/")
    rec = OtpSecret.objects.get(user=user_ok)
    assert rec.enabled is False
    assert rec.verified_at is None
    assert not Session.objects.filter(user=user_ok).exists()


@pytest.mark.django_db
def test_login_ldap_mfa_required(api, role, region, segment):
    assert _register_ad(api, region, segment).status_code == 200
    with patch("apps.iam.services.ldap_service.bind_user_dn"):
        r = api.post(
            "/api/v1/auth/login/ldap",
            {"email": "lucie.ad@yas.tg", "password": AD_PASSWORD, "device": DEVICE},
            format="json",
        )
    assert r.status_code == 200
    assert r.data["data"]["mfa_required"] is True
    assert "access_token" not in r.data["data"]


@pytest.mark.django_db
def test_enroll_verify_totp_returns_backup_once(api, user_ok):
    r = _login(api, email="jean.dupont@yas.tg")
    v = post_mfa_verify(api, mfa_token=r.data["data"]["mfa_token"], user=user_ok)
    assert v.status_code == 200
    data = v.data["data"]
    assert "access_token" in data
    codes = data["backup_codes"]
    assert len(codes) == 10
    rec = OtpSecret.objects.get(user=user_ok)
    assert rec.enabled is True
    assert rec.verified_at is not None
    assert hash_backup_code(codes[0]) in rec.backup_codes
    assert codes[0] not in rec.backup_codes


@pytest.mark.django_db
def test_second_login_verify_no_backup_codes(api, user_ok):
    login_until_jwt(api, email="jean.dupont@yas.tg", password=PASSWORD, device=DEVICE)
    r = _login(api, email="jean.dupont@yas.tg")
    assert r.data["data"]["enroll"] is False
    assert "otpauth_uri" not in r.data["data"]
    v = post_mfa_verify(api, mfa_token=r.data["data"]["mfa_token"], user=user_ok)
    assert v.status_code == 200
    assert "backup_codes" not in v.data["data"]
    assert "access_token" in v.data["data"]


@pytest.mark.django_db
def test_totp_invalid_401(api, user_ok):
    r = _login(api, email="jean.dupont@yas.tg")
    v = post_mfa_verify(
        api, mfa_token=r.data["data"]["mfa_token"], user=user_ok, otp="000000"
    )
    assert v.status_code == 401
    assert v.data["code"] == "INVALID_CREDENTIALS"
    assert v.data["message"] == MSG_INVALID
    assert not Session.objects.filter(user=user_ok).exists()
    assert LoginHistory.objects.filter(success=False, failure_reason="MFA_INVALID").exists()


@pytest.mark.django_db
def test_mfa_token_expired(api, user_ok):
    r = _login(api, email="jean.dupont@yas.tg")
    cache.clear()
    v = post_mfa_verify(api, mfa_token=r.data["data"]["mfa_token"], user=user_ok)
    assert v.status_code == 401
    assert v.data["code"] == "MFA_CHALLENGE_EXPIRED"


@pytest.mark.django_db
def test_backup_ok_then_replay(api, user_ok):
    first = login_until_jwt(api, email="jean.dupont@yas.tg", password=PASSWORD, device=DEVICE)
    code = first.data["data"]["backup_codes"][0]
    r = _login(api, email="jean.dupont@yas.tg")
    ok = post_mfa_verify(api, mfa_token=r.data["data"]["mfa_token"], backup_code=code)
    assert ok.status_code == 200
    assert "access_token" in ok.data["data"]
    rec = OtpSecret.objects.get(user=user_ok)
    assert hash_backup_code(code) not in rec.backup_codes
    r2 = _login(api, email="jean.dupont@yas.tg")
    replay = post_mfa_verify(api, mfa_token=r2.data["data"]["mfa_token"], backup_code=code)
    assert replay.status_code == 401
    assert replay.data["code"] == "INVALID_CREDENTIALS"


@pytest.mark.django_db
def test_backup_during_enroll_400(api, user_ok):
    r = _login(api, email="jean.dupont@yas.tg")
    v = post_mfa_verify(
        api, mfa_token=r.data["data"]["mfa_token"], backup_code="ABCD-EFGH"
    )
    assert v.status_code == 400
    assert v.data["code"] == "VALIDATION_ERROR"


@pytest.mark.django_db
def test_trusted_device_still_mfa(api, user_ok):
    login_until_jwt(api, email="jean.dupont@yas.tg", password=PASSWORD, device=DEVICE)
    device = Device.objects.get(user=user_ok, device_uuid="test-web-1")
    device.trusted = True
    device.save(update_fields=["trusted"])
    r = _login(api, email="jean.dupont@yas.tg")
    assert r.status_code == 200
    assert r.data["data"]["mfa_required"] is True
    assert "access_token" not in r.data["data"]


@pytest.mark.django_db
def test_register_ad_mfa_no_jwt(api, role, region, segment):
    r = _register_ad(api, region, segment)
    assert r.status_code == 200
    data = r.data["data"]
    assert data["mfa_required"] is True
    assert "access_token" not in data
    user = User.objects.get(email="lucie.ad@yas.tg")
    assert user.ldap_dn == IDENTITY.dn
    assert not Session.objects.filter(user=user).exists()


@pytest.mark.django_db
def test_refresh_after_mfa_no_otp(api, user_ok):
    first = login_until_jwt(api, email="jean.dupont@yas.tg", password=PASSWORD, device=DEVICE)
    r = api.post(
        "/api/v1/auth/refresh",
        {"refresh_token": first.data["data"]["refresh_token"]},
        format="json",
    )
    assert r.status_code == 200
    assert "access_token" in r.data["data"]
    assert "mfa_required" not in r.data["data"]


@pytest.mark.django_db
def test_admin_reset_mfa(api, user_ok, admin_ok):
    enrolled = login_until_jwt(
        api, email="jean.dupont@yas.tg", password=PASSWORD, device=DEVICE
    )
    assert Session.objects.filter(user=user_ok, is_active=True).exists()
    admin_tok = login_until_jwt(
        api, email="admin@yas.tg", password=ADMIN_PASSWORD, device=DEVICE
    ).data["data"]["access_token"]
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {admin_tok}")
    r = api.post(f"/api/v1/admin/users/{user_ok.id}/mfa/reset")
    assert r.status_code == 200
    assert not OtpSecret.objects.filter(user=user_ok).exists()
    assert not Session.objects.filter(user=user_ok, is_active=True).exists()
    assert AuditLog.objects.filter(action="MFA_RESET", entity_id=user_ok.id).exists()
    api.credentials()
    reuse = api.get(
        "/api/v1/admin/users",
        HTTP_AUTHORIZATION=f"Bearer {enrolled.data['data']['access_token']}",
    )
    assert reuse.status_code in (401, 403)
    again = _login(api, email="jean.dupont@yas.tg")
    assert again.data["data"]["enroll"] is True
    assert "otpauth_uri" in again.data["data"]


@pytest.mark.django_db
def test_user_cannot_reset_mfa(api, user_ok, admin_ok):
    tok = login_until_jwt(
        api, email="jean.dupont@yas.tg", password=PASSWORD, device=DEVICE
    ).data["data"]["access_token"]
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {tok}")
    r = api.post(f"/api/v1/admin/users/{admin_ok.id}/mfa/reset")
    assert r.status_code == 403


@pytest.mark.django_db
def test_jean_dupont_factor1_ldap_dn_null(api, user_ok):
    r = _login(api, email="jean.dupont@yas.tg")
    assert r.status_code == 200
    assert r.data["data"]["mfa_required"] is True
    user_ok.refresh_from_db()
    assert user_ok.ldap_dn is None


@pytest.mark.django_db
def test_health_and_docs(api, db):
    assert api.get("/health").status_code == 200
    assert api.get("/api/docs/").status_code == 200
    schema = api.get("/api/schema/")
    assert schema.status_code == 200
    text = schema.content.decode()
    assert "/api/v1/auth/mfa/verify" in text
    assert "/api/v1/auth/mfa/backup-codes/regenerate" in text
    assert "/api/v1/admin/users/{id}/mfa/reset" in text or "mfa/reset" in text


@pytest.mark.django_db
def test_admin_same_mfa_rule(api, admin_ok):
    r = api.post(
        "/api/v1/auth/login",
        {"email": "admin@yas.tg", "password": ADMIN_PASSWORD, "device": DEVICE},
        format="json",
    )
    assert r.status_code == 200
    assert r.data["data"]["mfa_required"] is True
    assert "access_token" not in r.data["data"]


@pytest.mark.django_db
def test_begin_mfa_rotates_secret_before_verify(api, user_ok):
    first = _login(api, email="jean.dupont@yas.tg")
    secret_a = decrypt_totp_secret(OtpSecret.objects.get(user=user_ok).secret)
    otp_a = pyotp.TOTP(secret_a, digits=6, interval=30).now()
    second = _login(api, email="jean.dupont@yas.tg")
    secret_b = decrypt_totp_secret(OtpSecret.objects.get(user=user_ok).secret)
    assert secret_a != secret_b
    stale = post_mfa_verify(api, mfa_token=first.data["data"]["mfa_token"], otp=otp_a)
    assert stale.status_code == 401
    ok = post_mfa_verify(api, mfa_token=second.data["data"]["mfa_token"], user=user_ok)
    assert ok.status_code == 200


@pytest.mark.django_db
def test_regen_backup_codes(api, user_ok):
    enrolled = login_until_jwt(
        api, email="jean.dupont@yas.tg", password=PASSWORD, device=DEVICE
    )
    old = enrolled.data["data"]["backup_codes"][0]
    token = enrolled.data["data"]["access_token"]
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    r = api.post(
        "/api/v1/auth/mfa/backup-codes/regenerate",
        {"otp": totp_now(user_ok)},
        format="json",
    )
    assert r.status_code == 200
    new_codes = r.data["data"]["backup_codes"]
    assert old not in new_codes
    assert AuditLog.objects.filter(action="MFA_BACKUP_REGEN", user=user_ok).exists()
    api.credentials()
    challenge = _login(api, email="jean.dupont@yas.tg")
    replay = post_mfa_verify(
        api, mfa_token=challenge.data["data"]["mfa_token"], backup_code=old
    )
    assert replay.status_code == 401
    challenge2 = _login(api, email="jean.dupont@yas.tg")
    ok = post_mfa_verify(
        api, mfa_token=challenge2.data["data"]["mfa_token"], backup_code=new_codes[0]
    )
    assert ok.status_code == 200


@pytest.mark.django_db
def test_no_user_delete_mfa_route(api, user_ok):
    assert api.delete("/api/v1/auth/mfa").status_code == 404
    assert api.post("/api/v1/auth/mfa/sms", {}, format="json").status_code == 404


@pytest.mark.django_db
def test_sixth_otp_rate_limited(api, user_ok):
    r = _login(api, email="jean.dupont@yas.tg")
    token = r.data["data"]["mfa_token"]
    for _ in range(5):
        bad = post_mfa_verify(api, mfa_token=token, otp="000000")
        assert bad.status_code == 401
    sixth = post_mfa_verify(api, mfa_token=token, otp="000000")
    assert sixth.status_code == 401
    assert sixth.data["code"] == "INVALID_CREDENTIALS"
    assert LoginHistory.objects.filter(failure_reason="RATE_LIMITED").exists()
