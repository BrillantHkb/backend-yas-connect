"""ANNUAIRE-A : people-picker GET /users + directory segment-types / parent_id."""

import pytest
from django.core.cache import cache
from django.core.management import call_command
from rest_framework.test import APIClient

from apps.annuaire.models import Segment, SegmentType
from apps.iam.helpers.compliance import close_gates
from apps.iam.helpers.mfa import login_until_jwt
from apps.iam.models import Region, Role, RolePermission, User, Visibility
from apps.iam.services.rbac_service import invalidate_role_cache

DEVICE = {"device_uuid": "test-web-1", "platform": "WEB"}
UA = "Mozilla/5.0 pytest"
PASSWORD = "Secret123!"


@pytest.fixture
def api():
    cache.clear()
    client = APIClient()
    client.defaults["HTTP_USER_AGENT"] = UA
    return client


@pytest.fixture
def user_role(db):
    return Role.objects.create(code="USER", name="Utilisateur", is_system=True, level=0)


def _make_user(user_role, *, email, username, first_name, last_name, gated=True, **extra):
    user = User.objects.create_user(
        email=email,
        password=PASSWORD,
        username=username,
        role=user_role,
        first_name=first_name,
        last_name=last_name,
        **extra,
    )
    return close_gates(user) if gated else user


@pytest.fixture
def jean(user_role):
    return _make_user(
        user_role, email="jean.dupont@yas.tg", username="jean.dupont",
        first_name="Jean", last_name="Dupont",
    )


@pytest.fixture
def marie(user_role):
    return _make_user(
        user_role, email="marie.koevi@yas.tg", username="marie.koevi",
        first_name="Marie", last_name="Koevi",
    )


def _jwt(api, user, *, password=PASSWORD, device=DEVICE):
    r = login_until_jwt(api, email=user.email, password=password, device=device)
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {r.data['data']['access_token']}")
    return r


@pytest.mark.django_db
def test_query_too_short(api, jean):
    _jwt(api, jean)
    assert api.get("/api/v1/users/").data["code"] == "QUERY_TOO_SHORT"
    assert api.get("/api/v1/users/?q=m").data["code"] == "QUERY_TOO_SHORT"
    assert api.get("/api/v1/users/?q=" + "a" * 65).data["code"] == "QUERY_TOO_SHORT"


@pytest.mark.django_db
def test_search_hit_no_email_no_self(api, jean, marie):
    _jwt(api, jean)
    r = api.get("/api/v1/users/?q=koe")
    assert r.status_code == 200
    data = r.data["data"]
    ids = [h["id"] for h in data["results"]]
    assert str(marie.id) in ids
    assert str(jean.id) not in ids
    hit = next(h for h in data["results"] if h["id"] == str(marie.id))
    assert "email" not in hit
    assert "phone" not in hit
    assert "matricule" not in hit
    assert hit["display_name"] == "Marie Koevi"
    assert hit["username"] == "marie.koevi"


@pytest.mark.django_db
def test_hit_photo_nobody_status_still_visible(api, jean, marie):
    priv = marie.privacy
    priv.profile_photo_visibility = Visibility.NOBODY
    priv.online_status_visibility = Visibility.EVERYONE
    priv.save(update_fields=["profile_photo_visibility", "online_status_visibility", "updated_at"])
    marie.status = User.PresenceStatus.ONLINE
    marie.save(update_fields=["status", "updated_at"])
    _jwt(api, jean)
    r = api.get("/api/v1/users/?q=koe")
    hit = next(h for h in r.data["data"]["results"] if h["id"] == str(marie.id))
    assert hit["avatar_url"] is None


@pytest.mark.django_db
def test_hit_online_status_nobody_hides_badge(api, jean, marie):
    priv = marie.privacy
    priv.online_status_visibility = Visibility.NOBODY
    priv.save(update_fields=["online_status_visibility", "updated_at"])
    _jwt(api, jean)
    r = api.get("/api/v1/users/?q=koe")
    hit = next(h for h in r.data["data"]["results"] if h["id"] == str(marie.id))
    assert hit["status"] is None
    assert hit["badge"] is None


@pytest.mark.django_db
def test_pending_and_disabled_absent(api, jean, user_role):
    pending = User.objects.create_user(
        email="pending.koevi@yas.tg", password=PASSWORD, username="pending.koevi",
        role=user_role, first_name="Pending", last_name="Koevi",
        pending_approval=True, is_active=False,
    )
    disabled = close_gates(
        User.objects.create_user(
            email="off.koevi@yas.tg", password=PASSWORD, username="off.koevi",
            role=user_role, first_name="Off", last_name="Koevi", is_active=False,
        )
    )
    _jwt(api, jean)
    r = api.get("/api/v1/users/?q=koe")
    ids = [h["id"] for h in r.data["data"]["results"]]
    assert str(pending.id) not in ids
    assert str(disabled.id) not in ids


@pytest.mark.django_db
def test_region_and_segment_filters_and(api, jean, marie):
    r1 = Region.objects.create(code="MARITIME", name="Maritime")
    r2 = Region.objects.create(code="PLATEAUX", name="Plateaux")
    st = SegmentType.objects.create(code="SERVICE", name="Service", level=2)
    seg1 = Segment.objects.create(code="NOC", name="NOC", segment_type=st, is_active=True)
    seg2 = Segment.objects.create(code="RH", name="RH", segment_type=st, is_active=True)
    marie.region = r1
    marie.segment_id = seg1.id
    marie.save(update_fields=["region", "segment_id", "updated_at"])
    _jwt(api, jean)

    ok = api.get(f"/api/v1/users/?q=koe&region_id={r1.id}&segment_id={seg1.id}")
    assert str(marie.id) in [h["id"] for h in ok.data["data"]["results"]]

    miss_region = api.get(f"/api/v1/users/?q=koe&region_id={r2.id}")
    assert str(marie.id) not in [h["id"] for h in miss_region.data["data"]["results"]]

    miss_segment = api.get(f"/api/v1/users/?q=koe&segment_id={seg2.id}")
    assert str(marie.id) not in [h["id"] for h in miss_segment.data["data"]["results"]]

    hit = next(h for h in ok.data["data"]["results"] if h["id"] == str(marie.id))
    assert hit["org"]["segment"]["code"] == "NOC"


@pytest.mark.django_db
def test_pagination_limit_offset(api, jean, user_role):
    for i in range(5):
        _make_user(
            user_role, email=f"koevi{i}@yas.tg", username=f"koevi{i}",
            first_name="Coll", last_name=f"Koevi{i}",
        )
    _jwt(api, jean)
    r = api.get("/api/v1/users/?q=koe&limit=2&offset=0")
    assert r.status_code == 200
    assert r.data["data"]["count"] == 5
    assert len(r.data["data"]["results"]) == 2
    r2 = api.get("/api/v1/users/?q=koe&limit=2&offset=4")
    assert len(r2.data["data"]["results"]) == 1


@pytest.mark.django_db
def test_fiche_id_contract_unchanged(api, jean, marie):
    _jwt(api, jean)
    r = api.get(f"/api/v1/users/{marie.id}")
    assert r.status_code == 200
    assert r.data["data"]["user"]["display_name"] == "Marie Koevi"


@pytest.mark.django_db
def test_directory_regions_public_maritime_first(api, db):
    Region.objects.create(code="PLATEAUX", name="Plateaux")
    Region.objects.create(code="MARITIME", name="Maritime")
    r = api.get("/api/v1/directory/regions")
    assert r.status_code == 200
    assert r.data["data"][0]["code"] == "MARITIME"


@pytest.mark.django_db
def test_directory_segment_types_public(api, db):
    call_command("seed_annuaire")
    r = api.get("/api/v1/directory/segment-types")
    assert r.status_code == 200
    assert r.data["data"][0]["code"] == "DIRECTION"
    assert r.data["data"][0]["level"] == 0


@pytest.mark.django_db
def test_directory_segments_roots_and_children(api, db):
    call_command("seed_annuaire")
    roots = api.get("/api/v1/directory/segments")
    assert roots.status_code == 200
    yas = next(s for s in roots.data["data"] if s["code"] == "YAS")
    assert yas["parent_id"] is None
    assert yas["type_code"] == "DIRECTION"

    children = api.get(f"/api/v1/directory/segments?parent_id={yas['id']}")
    assert children.status_code == 200
    assert children.data["data"] == []


@pytest.mark.django_db
def test_directory_segments_bad_parent_id(api, db):
    r = api.get("/api/v1/directory/segments?parent_id=not-a-uuid")
    assert r.status_code == 400
    assert r.data["code"] == "VALIDATION_ERROR"


@pytest.mark.django_db
def test_seed_annuaire_idempotent(db):
    call_command("seed_annuaire")
    call_command("seed_annuaire")
    assert SegmentType.objects.filter(code="DIRECTION").count() == 1
    assert Segment.objects.filter(code="YAS").count() == 1


@pytest.mark.django_db
def test_users_search_without_jwt_401(api, marie):
    r = api.get("/api/v1/users/?q=koe")
    assert r.status_code == 401


@pytest.mark.django_db
def test_users_search_without_permission_403(api, jean, marie):
    RolePermission.objects.filter(
        role=jean.role, permission__code="iam.profile.read_other"
    ).delete()
    invalidate_role_cache(jean.role_id)
    _jwt(api, jean)
    r = api.get("/api/v1/users/?q=koe")
    assert r.status_code == 403
    assert r.data["code"] == "FORBIDDEN"


@pytest.mark.django_db
def test_users_search_gates_before_tos_and_onboarding(api, user_role):
    fresh = User.objects.create_user(
        email="neuf@yas.tg", password=PASSWORD, username="user.neuf",
        role=user_role, first_name="Neuf", last_name="Compte",
    )
    _jwt(api, fresh)
    r = api.get("/api/v1/users/?q=koe")
    assert r.status_code == 403
    assert r.data["code"] == "TOS_REQUIRED"


@pytest.mark.django_db
def test_schema_has_annuaire_a_paths(api, db):
    schema = api.get("/api/schema/")
    assert schema.status_code == 200
    text = schema.content.decode()
    assert "/api/v1/users/" in text
    assert "segment-types" in text
