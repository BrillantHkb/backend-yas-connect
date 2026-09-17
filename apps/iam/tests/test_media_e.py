"""MEDIA-E : documents / GED (créer, lire, modifier, versions, aperçu)."""

import pytest
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from apps.iam.helpers.compliance import close_gates
from apps.iam.helpers.mfa import login_until_jwt
from apps.iam.models import Role, User
from apps.media.models import Document, DocumentVersion

PASSWORD = "Secret123!"
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


def _jwt(api, user, *, password=PASSWORD, device_uuid="web-1"):
    device = {"device_uuid": device_uuid, "platform": "WEB"}
    r = login_until_jwt(api, email=user.email, password=password, device=device)
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {r.data['data']['access_token']}")
    return r


def _upload_pdf(api, name="a.pdf", body=b"pdf-bytes"):
    r = api.post(
        "/api/v1/media/upload",
        {"file": SimpleUploadedFile(name, body, content_type="application/pdf")},
        format="multipart",
    )
    assert r.status_code == 201, r.data
    return r.data["data"]["id"]


@pytest.mark.django_db
def test_create_document(api, jean):
    _jwt(api, jean)
    upload_id = _upload_pdf(api)
    r = api.post(
        "/api/v1/documents",
        {"upload_id": upload_id, "title": "Contrat 2026", "category": "RH"},
        format="json",
    )
    assert r.status_code == 201
    assert r.data["data"]["version"] == 1
    document_id = r.data["data"]["id"]
    assert Document.objects.filter(pk=document_id).exists()
    assert DocumentVersion.objects.filter(document_id=document_id, version_number=1).exists()


@pytest.mark.django_db
def test_create_document_same_upload_twice_409(api, jean):
    _jwt(api, jean)
    upload_id = _upload_pdf(api)
    api.post("/api/v1/documents", {"upload_id": upload_id, "title": "V1"}, format="json")
    r = api.post("/api/v1/documents", {"upload_id": upload_id, "title": "V2"}, format="json")
    assert r.status_code == 409
    assert r.data["code"] == "ALREADY_DOCUMENT"


@pytest.mark.django_db
def test_create_document_other_user_upload_404(api, jean, marie):
    _jwt(api, marie)
    upload_id = _upload_pdf(api, name="marie.pdf")
    _jwt(api, jean)
    r = api.post("/api/v1/documents", {"upload_id": upload_id, "title": "Vol"}, format="json")
    assert r.status_code == 404


@pytest.mark.django_db
def test_get_document_non_owner_404(api, jean, marie):
    _jwt(api, jean)
    upload_id = _upload_pdf(api)
    document_id = api.post(
        "/api/v1/documents", {"upload_id": upload_id, "title": "Confidentiel"}, format="json"
    ).data["data"]["id"]
    _jwt(api, marie)
    r = api.get(f"/api/v1/documents/{document_id}")
    assert r.status_code == 404


@pytest.mark.django_db
def test_patch_document_title_and_confidential(api, jean):
    _jwt(api, jean)
    upload_id = _upload_pdf(api)
    document_id = api.post(
        "/api/v1/documents", {"upload_id": upload_id, "title": "Brouillon"}, format="json"
    ).data["data"]["id"]
    r = api.patch(
        f"/api/v1/documents/{document_id}",
        {"title": "Final", "confidential": True},
        format="json",
    )
    assert r.status_code == 200
    assert r.data["data"]["title"] == "Final"
    assert r.data["data"]["confidential"] is True


@pytest.mark.django_db
def test_patch_document_owner_transfer_revokes_old_owner(api, jean, marie):
    _jwt(api, jean)
    upload_id = _upload_pdf(api)
    document_id = api.post(
        "/api/v1/documents", {"upload_id": upload_id, "title": "Transfert"}, format="json"
    ).data["data"]["id"]
    r = api.patch(f"/api/v1/documents/{document_id}", {"owner_id": str(marie.id)}, format="json")
    assert r.status_code == 200
    assert r.data["data"]["owner_id"] == str(marie.id)

    old_owner_access = api.get(f"/api/v1/documents/{document_id}")
    assert old_owner_access.status_code == 404

    _jwt(api, marie)
    new_owner_access = api.get(f"/api/v1/documents/{document_id}")
    assert new_owner_access.status_code == 200


@pytest.mark.django_db
def test_add_version_increments_and_lists(api, jean):
    _jwt(api, jean)
    upload_id = _upload_pdf(api)
    document_id = api.post(
        "/api/v1/documents", {"upload_id": upload_id, "title": "Doc"}, format="json"
    ).data["data"]["id"]
    v2_upload = _upload_pdf(api, name="v2.pdf", body=b"v2-bytes")
    r = api.post(
        f"/api/v1/documents/{document_id}/versions",
        {"upload_id": v2_upload, "comment": "Correction typo"},
        format="json",
    )
    assert r.status_code == 201
    assert r.data["data"]["version_number"] == 2

    detail = api.get(f"/api/v1/documents/{document_id}")
    assert detail.data["data"]["version"] == 2

    versions = api.get(f"/api/v1/documents/{document_id}/versions")
    assert versions.status_code == 200
    assert len(versions.data["data"]["results"]) == 2
    assert versions.data["data"]["results"][0]["version_number"] == 2


@pytest.mark.django_db
def test_get_preview(api, jean):
    _jwt(api, jean)
    upload_id = _upload_pdf(api)
    document_id = api.post(
        "/api/v1/documents", {"upload_id": upload_id, "title": "Doc"}, format="json"
    ).data["data"]["id"]
    r = api.get(f"/api/v1/documents/{document_id}/preview")
    assert r.status_code == 200
    assert r.data["data"]["preview_url"]


@pytest.mark.django_db
def test_schema_has_documents_paths(api, db):
    schema = api.get("/api/schema/")
    assert schema.status_code == 200
    assert "/api/v1/documents" in schema.content.decode()
