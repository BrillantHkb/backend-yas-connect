"""AUTH-D : inscription AD / hors AD. LDAP mocké — pas de DC réel, pas de seed user AD."""

from unittest.mock import patch

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.annuaire.models import Segment, SegmentType
from apps.iam.helpers.compliance import close_gates
from apps.iam.helpers.mfa import login_until_jwt, post_mfa_verify
from apps.iam.models import AuditLog, Device, Region, Role, Session, User
from apps.iam.services.ldap_service import AdIdentity, DirectoryUnavailable, LdapBindFailed

DEVICE = {"device_uuid": "test-web-1", "platform": "WEB"}
UA = "Mozilla/5.0 pytest"
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
def admin_ok(admin_role):
    return close_gates(
        User.objects.create_user(
            email="admin@yas.tg",
            password="Admin123!",
            username="admin.yas",
            role=admin_role,
            first_name="Admin",
            last_name="YAS",
        )
    )


def _profile(region, segment, **extra):
    body = {
        "first_name": "Lucie",
        "last_name": "Ad",
        "phone": "+22890123456",
        "job_title": "Ingénieur NOC",
        "language": "fr",
        "region_id": str(region.id),
        "segment_id": str(segment.id),
        **extra,
    }
    return body


def _admin_bearer(api):
    login = login_until_jwt(
        api, email="admin@yas.tg", password="Admin123!", device=DEVICE
    )
    return login.data["data"]["access_token"]


@pytest.mark.django_db
@patch("apps.iam.services.register_service.bind_user_dn")
@patch("apps.iam.services.register_service.search_user_identity", return_value=IDENTITY)
def test_d01_bind_ok(mock_search, mock_bind, api):
    r = api.post(
        "/api/v1/auth/register/check-ad",
        {"email": "lucie.ad@yas.tg", "password": AD_PASSWORD},
        format="json",
    )
    assert r.status_code == 200
    assert r.data["data"]["ad_available"] is True
    mock_bind.assert_called_once()


@pytest.mark.django_db
@patch("apps.iam.services.register_service.bind_user_dn", side_effect=LdapBindFailed())
@patch("apps.iam.services.register_service.search_user_identity", return_value=IDENTITY)
def test_d01_bad_password(mock_search, mock_bind, api):
    r = api.post(
        "/api/v1/auth/register/check-ad",
        {"email": "lucie.ad@yas.tg", "password": "wrong"},
        format="json",
    )
    assert r.status_code == 200
    assert r.data["data"]["ad_available"] is False


@pytest.mark.django_db
@patch(
    "apps.iam.services.register_service.search_user_identity",
    side_effect=DirectoryUnavailable(),
)
def test_d01_ad_down(mock_search, api):
    r = api.post(
        "/api/v1/auth/register/check-ad",
        {"email": "lucie.ad@yas.tg", "password": AD_PASSWORD},
        format="json",
    )
    assert r.status_code == 503
    assert r.data["code"] == "DIRECTORY_UNAVAILABLE"


@pytest.mark.django_db
@patch("apps.iam.services.register_service.bind_user_dn")
@patch("apps.iam.services.register_service.search_user_identity", return_value=IDENTITY)
def test_d02_ok(mock_search, mock_bind, api, role, region, segment):
    r = api.post(
        "/api/v1/auth/register/ad",
        {
            "email": "lucie.ad@yas.tg",
            "password_ad": AD_PASSWORD,
            "password": APP_PASSWORD,
            "device": DEVICE,
            **_profile(region, segment),
        },
        format="json",
    )
    assert r.status_code == 200
    data = r.data["data"]
    assert data["mfa_required"] is True
    assert "access_token" not in data
    user = User.objects.get(email="lucie.ad@yas.tg")
    assert user.username == "lucie.ad"
    assert user.ldap_dn == IDENTITY.dn
    assert user.role.code == "USER"
    assert user.check_password(APP_PASSWORD)
    assert not user.check_password(AD_PASSWORD)
    assert Device.objects.filter(user=user).count() == 0
    assert not Session.objects.filter(user=user).exists()
    v = post_mfa_verify(api, mfa_token=data["mfa_token"], user=user)
    assert v.status_code == 200
    assert Device.objects.filter(user=user).count() == 1
    assert Session.objects.filter(user=user, login_method="PASSWORD", is_active=True).exists()


@pytest.mark.django_db
@patch("apps.iam.services.register_service.bind_user_dn")
@patch("apps.iam.services.register_service.search_user_identity", return_value=IDENTITY)
def test_d02_upn_taken(mock_search, mock_bind, api, role, region, segment):
    User.objects.create_user(
        email="lucie.ad@yas.tg",
        password=APP_PASSWORD,
        username="other",
        role=role,
    )
    r = api.post(
        "/api/v1/auth/register/ad",
        {
            "email": "lucie.ad@yas.tg",
            "password_ad": AD_PASSWORD,
            "password": APP_PASSWORD,
            "device": DEVICE,
            **_profile(region, segment),
        },
        format="json",
    )
    assert r.status_code == 409
    assert r.data["code"] == "CONFLICT"


@pytest.mark.django_db
@patch("apps.iam.services.register_service.bind_user_dn")
@patch("apps.iam.services.register_service.search_user_identity", return_value=IDENTITY)
def test_d02_weak_password(mock_search, mock_bind, api, role, region, segment):
    r = api.post(
        "/api/v1/auth/register/ad",
        {
            "email": "lucie.ad@yas.tg",
            "password_ad": AD_PASSWORD,
            "password": "Secret123",
            "device": DEVICE,
            **_profile(region, segment),
        },
        format="json",
    )
    assert r.status_code == 400
    assert r.data["code"] == "WEAK_PASSWORD"
    mock_search.assert_not_called()


@pytest.mark.django_db
def test_d02_missing_region(api, role, segment):
    r = api.post(
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
            "segment_id": str(segment.id),
        },
        format="json",
    )
    assert r.status_code == 400
    assert r.data["code"] == "VALIDATION_ERROR"


@pytest.mark.django_db
@patch("apps.iam.services.register_service.search_user_dn", side_effect=LdapBindFailed())
def test_d03_local(mock_search, api, role, region, segment):
    r = api.post(
        "/api/v1/auth/register",
        {
            "email": "marie.koevi@partenaire.tg",
            "password": APP_PASSWORD,
            **_profile(region, segment, first_name="Marie", last_name="Koevi"),
        },
        format="json",
    )
    assert r.status_code == 201
    data = r.data["data"]
    assert "access_token" not in data
    user = User.objects.get(email="marie.koevi@partenaire.tg")
    assert user.pending_approval is True
    assert user.is_active is False
    assert user.ldap_dn is None
    assert user.username.startswith("mkoevi")


@pytest.mark.django_db
@patch("apps.iam.services.register_service.search_user_dn", return_value=IDENTITY.dn)
def test_d03_ad_exists(mock_search, api, role, region, segment):
    r = api.post(
        "/api/v1/auth/register",
        {
            "email": "lucie.ad@yas.tg",
            "password": APP_PASSWORD,
            **_profile(region, segment),
        },
        format="json",
    )
    assert r.status_code == 409
    assert r.data["code"] == "AD_ACCOUNT_EXISTS"


@pytest.mark.django_db
@patch("apps.iam.services.register_service.search_user_dn", side_effect=LdapBindFailed())
def test_login_pending(mock_search, api, role, region, segment):
    api.post(
        "/api/v1/auth/register",
        {
            "email": "marie.koevi@partenaire.tg",
            "password": APP_PASSWORD,
            **_profile(region, segment, first_name="Marie", last_name="Koevi"),
        },
        format="json",
    )
    r = api.post(
        "/api/v1/auth/login",
        {"email": "marie.koevi@partenaire.tg", "password": APP_PASSWORD, "device": DEVICE},
        format="json",
    )
    assert r.status_code == 403
    assert r.data["code"] == "ACCOUNT_PENDING"


@pytest.mark.django_db
@patch("apps.iam.services.register_service.search_user_dn", side_effect=LdapBindFailed())
def test_d05_approve_then_login(mock_search, api, role, admin_ok, region, segment):
    api.post(
        "/api/v1/auth/register",
        {
            "email": "marie.koevi@partenaire.tg",
            "password": APP_PASSWORD,
            **_profile(region, segment, first_name="Marie", last_name="Koevi"),
        },
        format="json",
    )
    pending = User.objects.get(email="marie.koevi@partenaire.tg")
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {_admin_bearer(api)}")
    all_users = api.get("/api/v1/admin/users")
    assert all_users.status_code == 200
    emails = {row["email"] for row in all_users.data["data"]["results"]}
    assert "marie.koevi@partenaire.tg" in emails
    assert "admin@yas.tg" in emails
    listed = api.get("/api/v1/admin/users?pending=true")
    assert listed.status_code == 200
    assert listed.data["data"]["count"] == 1
    assert listed.data["data"]["results"][0]["email"] == "marie.koevi@partenaire.tg"
    ok = api.post(f"/api/v1/admin/users/{pending.id}/approve")
    assert ok.status_code == 200
    api.credentials()
    r = api.post(
        "/api/v1/auth/login",
        {"email": "marie.koevi@partenaire.tg", "password": APP_PASSWORD, "device": DEVICE},
        format="json",
    )
    assert r.status_code == 200
    assert r.data["data"]["mfa_required"] is True
    assert "access_token" not in r.data["data"]


@pytest.mark.django_db
@patch("apps.iam.services.register_service.search_user_dn", side_effect=LdapBindFailed())
def test_d05_reject_stays_inactive(mock_search, api, role, admin_ok, region, segment):
    api.post(
        "/api/v1/auth/register",
        {
            "email": "marie.koevi@partenaire.tg",
            "password": APP_PASSWORD,
            **_profile(region, segment, first_name="Marie", last_name="Koevi"),
        },
        format="json",
    )
    pending = User.objects.get(email="marie.koevi@partenaire.tg")
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {_admin_bearer(api)}")
    ok = api.post(
        f"/api/v1/admin/users/{pending.id}/reject",
        {"reason": "Profil incomplet"},
        format="json",
    )
    assert ok.status_code == 200
    pending.refresh_from_db()
    assert pending.is_active is False
    assert pending.pending_approval is True
    audit = AuditLog.objects.get(action="USER_REJECT", entity_id=pending.id)
    assert audit.metadata["reason"] == "Profil incomplet"
    api.credentials()
    r = api.post(
        "/api/v1/auth/login",
        {"email": "marie.koevi@partenaire.tg", "password": APP_PASSWORD, "device": DEVICE},
        format="json",
    )
    assert r.status_code == 403
    assert r.data["code"] == "ACCOUNT_PENDING"


@pytest.mark.django_db
def test_d05_reject_ldap_managed(api, role, admin_ok):
    user = User.objects.create_user(
        email="lucie.ad@yas.tg",
        password=APP_PASSWORD,
        username="lucie.ad",
        role=role,
        ldap_dn=IDENTITY.dn,
    )
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {_admin_bearer(api)}")
    r = api.post(
        f"/api/v1/admin/users/{user.id}/reject",
        {"reason": "ne doit pas passer"},
        format="json",
    )
    assert r.status_code == 400
    assert r.data["code"] == "LDAP_MANAGED"


@pytest.mark.django_db
def test_directory_public(api, region, segment):
    regions = api.get("/api/v1/directory/regions")
    segs = api.get("/api/v1/directory/segments")
    assert regions.status_code == 200
    assert segs.status_code == 200
    assert regions.data["data"][0]["code"] == "MARITIME"
    assert segs.data["data"][0]["code"] == "YAS"
