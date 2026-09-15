"""ANNUAIRE-C : CRUD admin historique affectations (user_segments) + delta AUTH-D/ADMIN-A."""

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.annuaire.models import Segment, SegmentType, UserSegment
from apps.iam.helpers.compliance import close_gates
from apps.iam.helpers.mfa import login_until_jwt
from apps.iam.models import Region, Role, User

PASSWORD = "Secret123!"
ADMIN_PASSWORD = "Admin123!"
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
def admin_role(db):
    return Role.objects.create(code="ADMIN", name="Administrateur", is_system=True, level=100)


@pytest.fixture
def region(db):
    return Region.objects.create(code="MARITIME", name="Maritime")


@pytest.fixture
def seed_types(db):
    return {
        "DIRECTION": SegmentType.objects.create(code="DIRECTION", name="Direction", level=0),
        "SERVICE": SegmentType.objects.create(code="SERVICE", name="Service", level=2),
    }


@pytest.fixture
def yas(seed_types):
    return Segment.objects.create(
        code="YAS", name="YAS Togo", segment_type=seed_types["DIRECTION"], is_active=True
    )


@pytest.fixture
def noc(seed_types, yas):
    return Segment.objects.create(
        code="NOC", name="NOC", segment_type=seed_types["SERVICE"], parent_segment=yas,
        is_active=True,
    )


@pytest.fixture
def jean(user_role, yas):
    return close_gates(
        User.objects.create_user(
            email="jean.dupont@yas.tg", password=PASSWORD, username="jean.dupont",
            role=user_role, first_name="Jean", last_name="Dupont", segment_id=yas.id,
        )
    )


@pytest.fixture
def admin_ok(admin_role):
    return close_gates(
        User.objects.create_user(
            email="admin@yas.tg", password=ADMIN_PASSWORD, username="admin.yas",
            role=admin_role, first_name="Admin", last_name="YAS",
        )
    )


def _jwt(api, user, *, password=PASSWORD, device=DEVICE):
    r = login_until_jwt(api, email=user.email, password=password, device=device)
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {r.data['data']['access_token']}")
    return r


def _admin(api, admin_ok):
    return _jwt(api, admin_ok, password=ADMIN_PASSWORD)


@pytest.mark.django_db
def test_history_two_lines_sorted(api, admin_ok, jean, yas, noc):
    UserSegment.objects.create(
        user=jean, segment=yas, is_active=False,
        start_date="2026-01-01T00:00:00Z", end_date="2026-06-01T00:00:00Z",
    )
    UserSegment.objects.create(
        user=jean, segment=noc, is_active=True, start_date="2026-06-01T00:00:00Z"
    )
    _admin(api, admin_ok)
    r = api.get(f"/api/v1/admin/users/{jean.id}/segments")
    assert r.status_code == 200
    rows = r.data["data"]["results"]
    assert len(rows) == 2
    assert rows[0]["segment"]["code"] == "NOC"
    assert rows[1]["segment"]["code"] == "YAS"


@pytest.mark.django_db
def test_post_mutation_closes_previous_and_syncs(api, admin_ok, jean, yas, noc):
    UserSegment.objects.create(
        user=jean, segment=yas, is_active=True, start_date="2026-01-01T00:00:00Z"
    )
    _admin(api, admin_ok)
    r = api.post(
        f"/api/v1/admin/users/{jean.id}/segments",
        {"segment_id": str(noc.id), "position": "Chef équipe"},
        format="json",
    )
    assert r.status_code == 201
    assert r.data["data"]["segment"]["code"] == "NOC"
    jean.refresh_from_db()
    assert str(jean.segment_id) == str(noc.id)
    old = UserSegment.objects.get(user=jean, segment=yas)
    assert old.is_active is False
    assert old.end_date is not None


@pytest.mark.django_db
def test_post_segment_invalid(api, admin_ok, jean):
    _admin(api, admin_ok)
    r = api.post(
        f"/api/v1/admin/users/{jean.id}/segments",
        {"segment_id": "5b1b1b1b-1b1b-1b1b-1b1b-1b1b1b1b1b1b"},
        format="json",
    )
    assert r.status_code == 400
    assert r.data["code"] == "SEGMENT_INVALID"


@pytest.mark.django_db
def test_patch_end_date_before_start_invalid(api, admin_ok, jean, yas):
    row = UserSegment.objects.create(
        user=jean, segment=yas, is_active=True, start_date="2026-06-01T00:00:00Z"
    )
    _admin(api, admin_ok)
    r = api.patch(
        f"/api/v1/admin/user-segments/{row.id}",
        {"end_date": "2026-01-01T00:00:00Z"},
        format="json",
    )
    assert r.status_code == 400
    assert r.data["code"] == "ASSIGNMENT_DATE_INVALID"


@pytest.mark.django_db
def test_delete_last_open_clears_users_segment_id(api, admin_ok, jean, yas):
    row = UserSegment.objects.create(
        user=jean, segment=yas, is_active=True, start_date="2026-01-01T00:00:00Z"
    )
    _admin(api, admin_ok)
    r = api.delete(f"/api/v1/admin/user-segments/{row.id}")
    assert r.status_code == 204
    jean.refresh_from_db()
    assert jean.segment_id is None


@pytest.mark.django_db
def test_register_local_opens_assignment(api, user_role, region, yas):
    body = {
        "email": "neuf@yas.tg",
        "password": "SecretApp456!",
        "first_name": "Neuf",
        "last_name": "Compte",
        "phone": "+22890111111",
        "job_title": "RH",
        "region_id": str(region.id),
        "segment_id": str(yas.id),
    }
    r = api.post("/api/v1/auth/register", body, format="json")
    assert r.status_code == 201
    user = User.objects.get(email="neuf@yas.tg")
    row = UserSegment.objects.get(user=user)
    assert row.assigned_by is None
    assert row.is_active is True
    assert str(user.segment_id) == str(yas.id)


@pytest.mark.django_db
def test_create_local_user_opens_assignment_with_admin_actor(api, user_role, admin_ok, region, yas):
    _admin(api, admin_ok)
    body = {
        "email": "marie.koevi@yas.tg",
        "password": "SecretApp456!",
        "first_name": "Marie",
        "last_name": "Koevi",
        "phone": "+22890111112",
        "job_title": "RH",
        "region_id": str(region.id),
        "segment_id": str(yas.id),
        "matricule": "TG2026100",
    }
    r = api.post("/api/v1/admin/users", body, format="json")
    assert r.status_code == 201
    user = User.objects.get(email="marie.koevi@yas.tg")
    row = UserSegment.objects.get(user=user)
    assert row.assigned_by_id == admin_ok.id


@pytest.mark.django_db
def test_region_invalid_on_create_regression(api, admin_ok, yas):
    _admin(api, admin_ok)
    body = {
        "email": "x@yas.tg",
        "password": "SecretApp456!",
        "first_name": "X",
        "last_name": "Y",
        "phone": "+22890111113",
        "job_title": "RH",
        "region_id": "5b1b1b1b-1b1b-1b1b-1b1b-1b1b1b1b1b1b",
        "segment_id": str(yas.id),
    }
    r = api.post("/api/v1/admin/users", body, format="json")
    assert r.status_code == 400
    assert r.data["code"] == "REGION_INVALID"


@pytest.mark.django_db
def test_segment_delete_blocked_by_user_segments(api, admin_ok, jean, yas):
    UserSegment.objects.create(
        user=jean, segment=yas, is_active=False, start_date="2026-01-01T00:00:00Z"
    )
    jean.segment_id = None
    jean.save(update_fields=["segment_id", "updated_at"])
    _admin(api, admin_ok)
    r = api.delete(f"/api/v1/admin/segments/{yas.id}")
    assert r.status_code == 409
    assert r.data["code"] == "SEGMENT_IN_USE"


@pytest.mark.django_db
def test_get_history_without_permission_403(api, jean):
    _jwt(api, jean)
    r = api.get(f"/api/v1/admin/users/{jean.id}/segments")
    assert r.status_code == 403
    assert r.data["code"] == "FORBIDDEN"


@pytest.mark.django_db
def test_patch_user_id_forbidden(api, admin_ok, jean, yas):
    row = UserSegment.objects.create(
        user=jean, segment=yas, is_active=True, start_date="2026-01-01T00:00:00Z"
    )
    _admin(api, admin_ok)
    r = api.patch(
        f"/api/v1/admin/user-segments/{row.id}",
        {"user_id": str(jean.id)},
        format="json",
    )
    assert r.status_code == 400
    assert r.data["code"] == "FIELD_FORBIDDEN"


@pytest.mark.django_db
def test_without_jwt_401(api, db):
    r = api.get("/api/v1/admin/segments")
    assert r.status_code == 401


@pytest.mark.django_db
def test_schema_has_annuaire_c_paths(api, db):
    schema = api.get("/api/schema/")
    assert schema.status_code == 200
    text = schema.content.decode()
    assert "/api/v1/admin/user-segments/{id}" in text or "/api/v1/admin/user-segments/{pk}" in text
