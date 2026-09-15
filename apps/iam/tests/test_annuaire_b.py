"""ANNUAIRE-B : CRUD admin segment-types / segments + arbre. Pas de porte AUTH-F."""

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.annuaire.models import Segment, SegmentType
from apps.iam.helpers.compliance import close_gates
from apps.iam.helpers.mfa import login_until_jwt
from apps.iam.models import Role, User

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
def jean(user_role):
    return close_gates(
        User.objects.create_user(
            email="jean.dupont@yas.tg", password=PASSWORD, username="jean.dupont",
            role=user_role, first_name="Jean", last_name="Dupont",
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


@pytest.fixture
def seed_types(db):
    return {
        "DIRECTION": SegmentType.objects.create(code="DIRECTION", name="Direction", level=0),
        "DEPARTEMENT": SegmentType.objects.create(code="DEPARTEMENT", name="Département", level=1),
        "SERVICE": SegmentType.objects.create(code="SERVICE", name="Service", level=2),
    }


@pytest.fixture
def yas(seed_types):
    return Segment.objects.create(
        code="YAS", name="YAS Togo", segment_type=seed_types["DIRECTION"], is_active=True
    )


def _jwt(api, user, *, password=PASSWORD, device=DEVICE):
    r = login_until_jwt(api, email=user.email, password=password, device=device)
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {r.data['data']['access_token']}")
    return r


def _admin(api, admin_ok):
    return _jwt(api, admin_ok, password=ADMIN_PASSWORD)


@pytest.mark.django_db
def test_user_forbidden_on_segment_types(api, jean):
    _jwt(api, jean)
    r = api.get("/api/v1/admin/segment-types")
    assert r.status_code == 403
    assert r.data["code"] == "FORBIDDEN"


@pytest.mark.django_db
def test_segment_type_code_taken(api, admin_ok, seed_types):
    _admin(api, admin_ok)
    r = api.post(
        "/api/v1/admin/segment-types", {"code": "DIRECTION", "name": "Autre"}, format="json"
    )
    assert r.status_code == 409
    assert r.data["code"] == "SEGMENT_TYPE_CODE_TAKEN"


@pytest.mark.django_db
def test_segment_type_delete_system_guard(api, admin_ok, seed_types):
    _admin(api, admin_ok)
    st = seed_types["SERVICE"]
    r = api.delete(f"/api/v1/admin/segment-types/{st.id}")
    assert r.status_code == 409
    assert r.data["code"] == "TYPE_SYSTEM"


@pytest.mark.django_db
def test_segment_type_create_then_delete(api, admin_ok):
    _admin(api, admin_ok)
    r = api.post(
        "/api/v1/admin/segment-types", {"code": "AGENCE", "name": "Agence", "level": 3},
        format="json",
    )
    assert r.status_code == 201
    type_id = r.data["data"]["id"]
    gone = api.delete(f"/api/v1/admin/segment-types/{type_id}")
    assert gone.status_code == 204
    assert not SegmentType.objects.filter(pk=type_id).exists()


@pytest.mark.django_db
def test_segment_type_delete_in_use(api, admin_ok, seed_types):
    Segment.objects.create(
        code="YAS", name="YAS Togo", segment_type=seed_types["DIRECTION"], is_active=True
    )
    st = SegmentType.objects.create(code="AGENCE", name="Agence", level=3)
    Segment.objects.create(code="AGENCE-1", name="Agence 1", segment_type=st, is_active=True)
    _admin(api, admin_ok)
    r = api.delete(f"/api/v1/admin/segment-types/{st.id}")
    assert r.status_code == 409
    assert r.data["code"] == "TYPE_IN_USE"


@pytest.mark.django_db
def test_segment_type_patch_code_immutable(api, admin_ok, seed_types):
    _admin(api, admin_ok)
    st = seed_types["SERVICE"]
    r = api.patch(f"/api/v1/admin/segment-types/{st.id}", {"code": "SVC"}, format="json")
    assert r.status_code == 400
    assert r.data["code"] == "CODE_IMMUTABLE"


@pytest.mark.django_db
def test_segment_create_child_of_yas(api, admin_ok, seed_types, yas):
    _admin(api, admin_ok)
    r = api.post(
        "/api/v1/admin/segments",
        {
            "code": "NOC-LOME",
            "name": "NOC Lomé",
            "segment_type_id": str(seed_types["DEPARTEMENT"].id),
            "parent_segment_id": str(yas.id),
        },
        format="json",
    )
    assert r.status_code == 201
    assert r.data["data"]["parent"]["code"] == "YAS"
    assert r.data["data"]["type"]["code"] == "DEPARTEMENT"


@pytest.mark.django_db
def test_segment_level_invalid(api, admin_ok, seed_types, yas):
    _admin(api, admin_ok)
    r = api.post(
        "/api/v1/admin/segments",
        {
            "code": "DSI",
            "name": "DSI",
            "segment_type_id": str(seed_types["DIRECTION"].id),
            "parent_segment_id": str(yas.id),
        },
        format="json",
    )
    assert r.status_code == 400
    assert r.data["code"] == "SEGMENT_LEVEL_INVALID"


@pytest.mark.django_db
def test_segment_patch_parent_self(api, admin_ok, yas):
    _admin(api, admin_ok)
    r = api.patch(
        f"/api/v1/admin/segments/{yas.id}",
        {"parent_segment_id": str(yas.id)},
        format="json",
    )
    assert r.status_code == 400
    assert r.data["code"] == "SEGMENT_PARENT_SELF"


@pytest.mark.django_db
def test_segment_patch_cycle(api, admin_ok, seed_types, yas):
    child = Segment.objects.create(
        code="NOC", name="NOC", segment_type=seed_types["SERVICE"], parent_segment=yas,
        is_active=True,
    )
    _admin(api, admin_ok)
    r = api.patch(
        f"/api/v1/admin/segments/{yas.id}",
        {"parent_segment_id": str(child.id)},
        format="json",
    )
    assert r.status_code == 400
    assert r.data["code"] == "SEGMENT_CYCLE"


@pytest.mark.django_db
def test_segment_create_responsable_inactive(api, admin_ok, user_role, yas):
    inactive = User.objects.create_user(
        email="off@yas.tg", password=PASSWORD, username="off.user",
        role=user_role, is_active=False,
    )
    _admin(api, admin_ok)
    r = api.post(
        "/api/v1/admin/segments",
        {"code": "NOC", "name": "NOC", "responsable_id": str(inactive.id)},
        format="json",
    )
    assert r.status_code == 400
    assert r.data["code"] == "RESPONSABLE_INVALID"


@pytest.mark.django_db
def test_segment_delete_in_use_by_user(api, admin_ok, jean, yas):
    jean.segment_id = yas.id
    jean.save(update_fields=["segment_id", "updated_at"])
    _admin(api, admin_ok)
    r = api.delete(f"/api/v1/admin/segments/{yas.id}")
    assert r.status_code == 409
    assert r.data["code"] == "SEGMENT_IN_USE"


@pytest.mark.django_db
def test_segment_delete_in_use_by_child(api, admin_ok, seed_types, yas):
    Segment.objects.create(
        code="NOC", name="NOC", segment_type=seed_types["SERVICE"], parent_segment=yas,
        is_active=True,
    )
    _admin(api, admin_ok)
    r = api.delete(f"/api/v1/admin/segments/{yas.id}")
    assert r.status_code == 409
    assert r.data["code"] == "SEGMENT_IN_USE"


@pytest.mark.django_db
def test_tree_nested_and_inactive_filtered(api, admin_ok, seed_types, yas):
    active_child = Segment.objects.create(
        code="NOC", name="NOC", segment_type=seed_types["SERVICE"], parent_segment=yas,
        is_active=True,
    )
    Segment.objects.create(
        code="RH", name="RH", segment_type=seed_types["SERVICE"], parent_segment=yas,
        is_active=False,
    )
    _admin(api, admin_ok)
    r = api.get("/api/v1/admin/segments/tree")
    assert r.status_code == 200
    root = next(n for n in r.data["data"] if n["code"] == "YAS")
    codes = [c["code"] for c in root["children"]]
    assert codes == [active_child.code]

    full = api.get("/api/v1/admin/segments/tree?include_inactive=true")
    root2 = next(n for n in full.data["data"] if n["code"] == "YAS")
    assert sorted(c["code"] for c in root2["children"]) == ["NOC", "RH"]


@pytest.mark.django_db
def test_directory_and_resolve_org_unaffected(api, admin_ok, jean, seed_types, yas):
    _admin(api, admin_ok)
    api.post(
        "/api/v1/admin/segments",
        {
            "code": "NOC",
            "name": "NOC",
            "segment_type_id": str(seed_types["SERVICE"].id),
            "parent_segment_id": str(yas.id),
        },
        format="json",
    )
    public = api.get("/api/v1/directory/segments")
    assert public.status_code == 200
    codes = {s["code"] for s in public.data["data"]}
    assert "YAS" in codes

    jean.segment_id = yas.id
    jean.save(update_fields=["segment_id", "updated_at"])
    _jwt(api, jean)
    me = api.get("/api/v1/me/")
    assert me.data["data"]["user"]["org"]["segment"]["code"] == "YAS"


@pytest.mark.django_db
def test_without_jwt_401(api, db):
    r = api.get("/api/v1/admin/segments")
    assert r.status_code == 401


@pytest.mark.django_db
def test_schema_has_annuaire_b_paths(api, db):
    schema = api.get("/api/schema/")
    assert schema.status_code == 200
    text = schema.content.decode()
    assert "/api/v1/admin/segments/tree" in text
    assert "/api/v1/admin/segment-types" in text
