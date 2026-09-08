"""AUTH-B : login LDAP + job AUTH-16. User AD via D02 mock (jamais seed_iam)."""

from unittest.mock import patch

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.annuaire.models import Segment, SegmentType
from apps.iam.jobs import sync_ldap_accounts
from apps.iam.models import AuditLog, Device, LoginHistory, Region, Role, Session, User
from apps.iam.services.ldap_service import (
    ADS_UF_ACCOUNTDISABLE,
    ADS_UF_LOCKOUT,
    ADS_UF_NORMAL_ACCOUNT,
    ADS_UF_PASSWORD_EXPIRED,
    ADS_UF_SMARTCARD_REQUIRED,
    ADS_UF_WORKSTATION_TRUST_ACCOUNT,
    AdIdentity,
    DirectoryUnavailable,
    LdapBindFailed,
    ad_logon_status,
    is_account_expired,
)
from apps.iam.tests.mfa_helpers import post_mfa_verify

DEVICE = {"device_uuid": "test-web-1", "platform": "WEB"}
UA = "Mozilla/5.0 pytest"
APP_PASSWORD = "SecretApp123!"
AD_PASSWORD = "WindowsPass1!"
PASSWORD_A = "Secret123!"
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
def region(db):
    return Region.objects.create(code="MARITIME", name="Maritime")


@pytest.fixture
def segment(db):
    st = SegmentType.objects.create(code="DIRECTION", name="Direction", level=0)
    return Segment.objects.create(code="YAS", name="YAS Togo", segment_type=st, is_active=True)


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
def test_login_ldap_ok_after_d02(api, role, region, segment):
    assert _register_ad(api, region, segment).status_code == 200
    with (
        patch("apps.iam.services.ldap_service.bind_user_dn") as mock_bind,
        patch("apps.iam.services.ldap_service.search_user_dn") as mock_search,
    ):
        r = api.post(
            "/api/v1/auth/login/ldap",
            {"email": "lucie.ad@yas.tg", "password": AD_PASSWORD, "device": DEVICE},
            format="json",
        )
    assert r.status_code == 200
    assert r.data["data"]["mfa_required"] is True
    assert "access_token" not in r.data["data"]
    mock_bind.assert_called()
    mock_search.assert_not_called()
    user = User.objects.get(email="lucie.ad@yas.tg")
    assert user.ldap_dn == IDENTITY.dn
    assert not Session.objects.filter(user=user).exists()
    v = post_mfa_verify(api, mfa_token=r.data["data"]["mfa_token"], user=user)
    assert v.status_code == 200
    assert Session.objects.filter(user=user, login_method="LDAP", is_active=True).count() == 1
    assert Device.objects.filter(user=user).count() == 1


@pytest.mark.django_db
def test_login_ldap_unknown_no_ad_call(api, role):
    with patch("apps.iam.services.ldap_service.search_user_dn") as mock_search:
        r = api.post(
            "/api/v1/auth/login/ldap",
            {"email": "inconnu@yas.tg", "password": AD_PASSWORD, "device": DEVICE},
            format="json",
        )
    assert r.status_code == 401
    assert r.data["message"] == MSG_INVALID
    mock_search.assert_not_called()
    assert LoginHistory.objects.filter(success=False, login_method="LDAP").exists()


@pytest.mark.django_db
def test_login_ldap_bind_ko(api, role, region, segment):
    _register_ad(api, region, segment)
    with patch("apps.iam.services.ldap_service.bind_user_dn", side_effect=LdapBindFailed()):
        with patch("apps.iam.services.ldap_service.search_user_dn", side_effect=LdapBindFailed()):
            r = api.post(
                "/api/v1/auth/login/ldap",
                {"email": "lucie.ad@yas.tg", "password": "bad", "device": DEVICE},
                format="json",
            )
    assert r.status_code == 401
    assert r.data["code"] == "INVALID_CREDENTIALS"


@pytest.mark.django_db
def test_login_ldap_ad_down(api, role, region, segment):
    _register_ad(api, region, segment)
    with patch("apps.iam.services.ldap_service.bind_user_dn", side_effect=DirectoryUnavailable()):
        r = api.post(
            "/api/v1/auth/login/ldap",
            {"email": "lucie.ad@yas.tg", "password": AD_PASSWORD, "device": DEVICE},
            format="json",
        )
    assert r.status_code == 503
    assert r.data["code"] == "DIRECTORY_UNAVAILABLE"


@pytest.mark.django_db
def test_login_ldap_disabled_after_bind(api, role, region, segment):
    _register_ad(api, region, segment)
    user = User.objects.get(email="lucie.ad@yas.tg")
    user.is_active = False
    user.save(update_fields=["is_active"])
    with patch("apps.iam.services.ldap_service.bind_user_dn"):
        r = api.post(
            "/api/v1/auth/login/ldap",
            {"email": "lucie.ad@yas.tg", "password": AD_PASSWORD, "device": DEVICE},
            format="json",
        )
    assert r.status_code == 403
    assert r.data["code"] == "ACCOUNT_DISABLED"


@pytest.mark.django_db
def test_login_ldap_uac_disable_401(api, role):
    User.objects.create_user(
        email="uac@yas.tg",
        password=APP_PASSWORD,
        username="uac.user",
        role=role,
    )
    with patch("apps.iam.services.ldap_service.search_user_dn", side_effect=LdapBindFailed()):
        r = api.post(
            "/api/v1/auth/login/ldap",
            {"email": "uac@yas.tg", "password": AD_PASSWORD, "device": DEVICE},
            format="json",
        )
    assert r.status_code == 401
    assert r.data["code"] == "INVALID_CREDENTIALS"
    assert not Session.objects.filter(user__email="uac@yas.tg").exists()


@pytest.mark.django_db
def test_job_dn_missing_disables(role):
    user = User.objects.create_user(
        email="sync@yas.tg",
        password=APP_PASSWORD,
        username="sync.user",
        role=role,
        ldap_dn=IDENTITY.dn,
    )
    local = User.objects.create_user(
        email="jean.dupont@yas.tg",
        password=PASSWORD_A,
        username="jean.dupont",
        role=role,
    )
    with patch("apps.iam.jobs.iter_ad_logon_state", return_value={}):
        sync_ldap_accounts()
    user.refresh_from_db()
    local.refresh_from_db()
    assert user.is_active is False
    assert local.is_active is True
    assert local.ldap_dn is None
    assert AuditLog.objects.filter(
        action="USER_LDAP_DISABLE", metadata__reason="DN_MISSING"
    ).exists()


@pytest.mark.django_db
def test_job_uac_disable(role):
    user = User.objects.create_user(
        email="sync2@yas.tg",
        password=APP_PASSWORD,
        username="sync2",
        role=role,
        ldap_dn=IDENTITY.dn,
    )
    with patch("apps.iam.jobs.iter_ad_logon_state", return_value={IDENTITY.dn: "DISABLED"}):
        sync_ldap_accounts()
    user.refresh_from_db()
    assert user.is_active is False
    assert AuditLog.objects.filter(metadata__reason="DISABLED").exists()


@pytest.mark.django_db
def test_auth_a_jean_intact(api, role):
    user = User.objects.create_user(
        email="jean.dupont@yas.tg",
        password=PASSWORD_A,
        username="jean.dupont",
        role=role,
    )
    r = api.post(
        "/api/v1/auth/login",
        {"email": "jean.dupont@yas.tg", "password": PASSWORD_A, "device": DEVICE},
        format="json",
    )
    assert r.status_code == 200
    assert r.data["data"]["mfa_required"] is True
    assert "access_token" not in r.data["data"]
    user.refresh_from_db()
    assert user.ldap_dn is None


@pytest.mark.django_db
def test_health_and_docs(api, db):
    assert api.get("/health").status_code == 200
    assert api.get("/api/docs/").status_code == 200
    schema = api.get("/api/schema/")
    assert schema.status_code == 200
    text = schema.content.decode()
    assert "/api/v1/auth/login/ldap" in text
    assert "/api/v1/auth/register/ad" in text


def test_ad_logon_status_bits():
    assert (
        ad_logon_status(user_account_control=ADS_UF_NORMAL_ACCOUNT, account_expires=0)
        == "USABLE"
    )
    assert (
        ad_logon_status(
            user_account_control=ADS_UF_NORMAL_ACCOUNT | ADS_UF_ACCOUNTDISABLE,
            account_expires=0,
        )
        == "DISABLED"
    )
    assert (
        ad_logon_status(
            user_account_control=ADS_UF_NORMAL_ACCOUNT | ADS_UF_LOCKOUT,
            account_expires=0,
        )
        == "LOCKED"
    )
    assert (
        ad_logon_status(
            user_account_control=ADS_UF_NORMAL_ACCOUNT | ADS_UF_PASSWORD_EXPIRED,
            account_expires=0,
        )
        == "PWD_EXPIRED"
    )
    assert (
        ad_logon_status(
            user_account_control=ADS_UF_NORMAL_ACCOUNT | ADS_UF_SMARTCARD_REQUIRED,
            account_expires=0,
        )
        == "SMARTCARD"
    )
    assert (
        ad_logon_status(
            user_account_control=ADS_UF_WORKSTATION_TRUST_ACCOUNT, account_expires=0
        )
        == "WRONG_TYPE"
    )
    assert is_account_expired(0) is False
    assert is_account_expired(0x7FFFFFFFFFFFFFFF) is False


@pytest.mark.django_db
def test_job_directory_down_no_mass_disable(role):
    user = User.objects.create_user(
        email="keep@yas.tg",
        password=APP_PASSWORD,
        username="keep",
        role=role,
        ldap_dn=IDENTITY.dn,
    )
    with patch("apps.iam.jobs.iter_ad_logon_state", side_effect=DirectoryUnavailable()):
        with pytest.raises(DirectoryUnavailable):
            sync_ldap_accounts()
    user.refresh_from_db()
    assert user.is_active is True
