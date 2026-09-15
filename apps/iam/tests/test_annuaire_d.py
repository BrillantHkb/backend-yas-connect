"""ANNUAIRE-D : CRUD self /me/skills+/me/certifications + admin équivalent (ANN-14,15,17,18)."""

import datetime

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.annuaire.models import UserCertification, UserSkill
from apps.iam.helpers.compliance import close_gates
from apps.iam.helpers.mfa import login_until_jwt
from apps.iam.models import Role, User
from apps.media.models import MediaFile

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
def marie(user_role):
    return close_gates(
        User.objects.create_user(
            email="marie.koevi@yas.tg", password=PASSWORD, username="marie.koevi",
            role=user_role, first_name="Marie", last_name="Koevi",
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


# --- ANN-17 : self skills -----------------------------------------------------


@pytest.mark.django_db
def test_self_post_skill_then_list(api, jean):
    _jwt(api, jean)
    r = api.post("/api/v1/me/skills", {"skill_name": "Fibre", "level": 4}, format="json")
    assert r.status_code == 201
    assert r.data["data"]["skill_name"] == "Fibre"
    r = api.get("/api/v1/me/skills")
    assert r.status_code == 200
    assert r.data["data"]["count"] == 1


@pytest.mark.django_db
def test_self_post_skill_duplicate_409(api, jean):
    _jwt(api, jean)
    api.post("/api/v1/me/skills", {"skill_name": "Fibre", "level": 2}, format="json")
    r = api.post("/api/v1/me/skills", {"skill_name": "fibre"}, format="json")
    assert r.status_code == 409
    assert r.data["code"] == "SKILL_TAKEN"


@pytest.mark.django_db
def test_self_post_skill_level_invalid(api, jean):
    _jwt(api, jean)
    r = api.post("/api/v1/me/skills", {"skill_name": "Fibre", "level": 9}, format="json")
    assert r.status_code == 400
    assert r.data["code"] == "SKILL_LEVEL_INVALID"


@pytest.mark.django_db
def test_self_patch_skill_of_another_user_404(api, jean, marie):
    row = UserSkill.objects.create(user=marie, skill_name="Fibre", level=3)
    _jwt(api, jean)
    r = api.patch(f"/api/v1/me/skills/{row.id}", {"level": 5}, format="json")
    assert r.status_code == 404


@pytest.mark.django_db
def test_self_skill_limit(api, jean):
    _jwt(api, jean)
    for i in range(50):
        UserSkill.objects.create(user=jean, skill_name=f"Skill{i}", level=1)
    r = api.post("/api/v1/me/skills", {"skill_name": "Skill50"}, format="json")
    assert r.status_code == 400
    assert r.data["code"] == "SKILL_LIMIT"


# --- ANN-14 : admin skills -----------------------------------------------------


@pytest.mark.django_db
def test_admin_post_skill_on_marie(api, admin_ok, marie):
    _admin(api, admin_ok)
    r = api.post(f"/api/v1/admin/users/{marie.id}/skills", {"skill_name": "Fibre"}, format="json")
    assert r.status_code == 201
    assert UserSkill.objects.get(user=marie).skill_name == "Fibre"


@pytest.mark.django_db
def test_jean_forbidden_on_admin_skills(api, jean, marie):
    _jwt(api, jean)
    r = api.get(f"/api/v1/admin/users/{marie.id}/skills")
    assert r.status_code == 403
    assert r.data["code"] == "FORBIDDEN"


# --- ANN-18 : self + admin certifications --------------------------------------


@pytest.mark.django_db
def test_self_certification_document_other_owner_invalid(api, jean, marie):
    media = MediaFile.objects.create(
        owner=marie, storage_path="certs/x.pdf", scan_status=MediaFile.ScanStatus.CLEAN,
    )
    _jwt(api, jean)
    r = api.post(
        "/api/v1/me/certifications",
        {"certification_name": "CCNA", "document_id": str(media.id)},
        format="json",
    )
    assert r.status_code == 400
    assert r.data["code"] == "CERT_DOCUMENT_INVALID"


@pytest.mark.django_db
def test_self_certification_document_scan_pending_invalid(api, jean):
    media = MediaFile.objects.create(
        owner=jean, storage_path="certs/x.pdf", scan_status=MediaFile.ScanStatus.PENDING,
    )
    _jwt(api, jean)
    r = api.post(
        "/api/v1/me/certifications",
        {"certification_name": "CCNA", "document_id": str(media.id)},
        format="json",
    )
    assert r.status_code == 400
    assert r.data["code"] == "CERT_DOCUMENT_INVALID"


@pytest.mark.django_db
def test_self_certification_document_success(api, jean):
    media = MediaFile.objects.create(
        owner=jean,
        storage_path="certs/x.pdf",
        media_type=MediaFile.MediaType.DOCUMENT,
        scan_status=MediaFile.ScanStatus.CLEAN,
    )
    _jwt(api, jean)
    r = api.post(
        "/api/v1/me/certifications",
        {"certification_name": "CCNA", "document_id": str(media.id)},
        format="json",
    )
    assert r.status_code == 201
    assert r.data["data"]["document"]["id"] == str(media.id)


@pytest.mark.django_db
def test_self_certification_document_wrong_media_type_invalid(api, jean):
    media = MediaFile.objects.create(
        owner=jean,
        storage_path="avatars/x.jpg",
        media_type=MediaFile.MediaType.IMAGE,
        scan_status=MediaFile.ScanStatus.CLEAN,
    )
    _jwt(api, jean)
    r = api.post(
        "/api/v1/me/certifications",
        {"certification_name": "CCNA", "document_id": str(media.id)},
        format="json",
    )
    assert r.status_code == 400
    assert r.data["code"] == "CERT_DOCUMENT_INVALID"


@pytest.mark.django_db
def test_self_certification_issued_at_future_invalid(api, jean):
    _jwt(api, jean)
    tomorrow = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
    r = api.post(
        "/api/v1/me/certifications",
        {"certification_name": "CCNA", "issued_at": tomorrow},
        format="json",
    )
    assert r.status_code == 400
    assert r.data["code"] == "CERT_DATE_INVALID"


@pytest.mark.django_db
def test_self_delete_certification_keeps_media_file(api, jean):
    media = MediaFile.objects.create(
        owner=jean, storage_path="certs/x.pdf", scan_status=MediaFile.ScanStatus.CLEAN,
    )
    row = UserCertification.objects.create(user=jean, certification_name="CCNA", document=media)
    _jwt(api, jean)
    r = api.delete(f"/api/v1/me/certifications/{row.id}")
    assert r.status_code == 204
    assert MediaFile.objects.filter(pk=media.id).exists()


@pytest.mark.django_db
def test_jean_forbidden_on_admin_certifications(api, jean, marie):
    _jwt(api, jean)
    r = api.get(f"/api/v1/admin/users/{marie.id}/certifications")
    assert r.status_code == 403
    assert r.data["code"] == "FORBIDDEN"


@pytest.mark.django_db
def test_admin_get_certifications_of_jean(api, admin_ok, jean):
    UserCertification.objects.create(user=jean, certification_name="CCNA")
    _admin(api, admin_ok)
    r = api.get(f"/api/v1/admin/users/{jean.id}/certifications")
    assert r.status_code == 200
    assert r.data["data"]["count"] == 1


# --- Portes / auth --------------------------------------------------------------


@pytest.mark.django_db
def test_self_without_tos_403(api, user_role):
    fresh = User.objects.create_user(
        email="fresh@yas.tg", password=PASSWORD, username="fresh.user",
        role=user_role, first_name="Fresh", last_name="User",
    )
    _jwt(api, fresh)
    r = api.post("/api/v1/me/skills", {"skill_name": "Fibre"}, format="json")
    assert r.status_code == 403
    assert r.data["code"] == "TOS_REQUIRED"


@pytest.mark.django_db
def test_without_jwt_401(api, db):
    r = api.get("/api/v1/me/skills")
    assert r.status_code == 401


@pytest.mark.django_db
def test_schema_has_annuaire_d_paths(api, db):
    schema = api.get("/api/schema/")
    assert schema.status_code == 200
    text = schema.content.decode()
    assert "/api/v1/me/skills" in text
    assert (
        "/api/v1/admin/user-certifications/{id}" in text
        or "/api/v1/admin/user-certifications/{pk}" in text
    )
