"""MEDIA-R + MEDIA-A : upload presigné + multipart direct sur MinIO réel."""

import hashlib
import urllib.request

import pytest
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from apps.iam.helpers.compliance import close_gates
from apps.iam.helpers.mfa import login_until_jwt
from apps.iam.models import Role, RolePermission, User
from apps.iam.services.rbac_service import invalidate_role_cache
from apps.media.models import MediaAccessLog, MediaFile, StorageUsage
from apps.media.services import storage

PASSWORD = "Secret123!"
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


def _jwt(api, user, *, password=PASSWORD, device=DEVICE):
    r = login_until_jwt(api, email=user.email, password=password, device=device)
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {r.data['data']['access_token']}")
    return r


def _put(url: str, data: bytes, content_type: str) -> None:
    headers = {"Content-Type": content_type}
    req = urllib.request.Request(url, data=data, method="PUT", headers=headers)
    urllib.request.urlopen(req, timeout=10).close()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _init_body(size_bytes, *, filename="a.txt", mime_type="text/plain", media_type="DOCUMENT"):
    return {
        "filename": filename, "mime_type": mime_type,
        "size_bytes": size_bytes, "media_type": media_type,
    }


# --- MED-01 : init presign ----------------------------------------------------


@pytest.mark.django_db
def test_init_presign_ok(api, jean):
    _jwt(api, jean)
    r = api.post(
        "/api/v1/media/uploads", _init_body(1000, filename="a.pdf", mime_type="application/pdf"),
        format="json",
    )
    assert r.status_code == 201
    assert r.data["data"]["upload_id"]
    assert r.data["data"]["presigned_url"]


@pytest.mark.django_db
def test_init_presign_too_large(api, jean):
    _jwt(api, jean)
    r = api.post(
        "/api/v1/media/uploads",
        _init_body(999_999_999, filename="a.pdf", mime_type="application/pdf"),
        format="json",
    )
    assert r.status_code == 413
    assert r.data["code"] == "FILE_TOO_LARGE"


@pytest.mark.django_db
def test_init_presign_invalid_media_type(api, jean):
    _jwt(api, jean)
    r = api.post(
        "/api/v1/media/uploads",
        _init_body(1000, filename="a.pdf", mime_type="application/pdf", media_type="NOPE"),
        format="json",
    )
    assert r.status_code == 400
    assert r.data["code"] == "VALIDATION_ERROR"


@pytest.mark.django_db
def test_presign_full_roundtrip(api, jean):
    _jwt(api, jean)
    body = b"hello yas connect"
    init = api.post("/api/v1/media/uploads", _init_body(len(body)), format="json")
    upload_id = init.data["data"]["upload_id"]
    _put(init.data["data"]["presigned_url"], body, "text/plain")

    r = api.post(
        f"/api/v1/media/uploads/{upload_id}/complete",
        {"checksum": _sha256(body)},
        format="json",
    )
    assert r.status_code == 200
    assert r.data["data"]["scan_status"] == "SKIPPED"
    assert r.data["data"]["checksum"] == _sha256(body)


@pytest.mark.django_db
def test_complete_without_put_incomplete(api, jean):
    _jwt(api, jean)
    init = api.post("/api/v1/media/uploads", _init_body(10), format="json")
    upload_id = init.data["data"]["upload_id"]
    r = api.post(
        f"/api/v1/media/uploads/{upload_id}/complete",
        {"checksum": _sha256(b"never-put-to-storage")},
        format="json",
    )
    assert r.status_code == 400
    assert r.data["code"] == "UPLOAD_INCOMPLETE"


@pytest.mark.django_db
def test_complete_twice_already_completed(api, jean):
    _jwt(api, jean)
    body = b"once"
    init = api.post("/api/v1/media/uploads", _init_body(len(body)), format="json")
    upload_id = init.data["data"]["upload_id"]
    complete_url = f"/api/v1/media/uploads/{upload_id}/complete"
    _put(init.data["data"]["presigned_url"], body, "text/plain")
    api.post(complete_url, {"checksum": _sha256(body)}, format="json")
    r = api.post(complete_url, {"checksum": _sha256(body)}, format="json")
    assert r.status_code == 409
    assert r.data["code"] == "ALREADY_COMPLETED"


@pytest.mark.django_db
def test_complete_duplicate_checksum(api, jean):
    _jwt(api, jean)
    body = b"duplicate-me"
    first = api.post(
        "/api/v1/media/upload",
        {"file": SimpleUploadedFile("a.txt", body, content_type="text/plain")},
        format="multipart",
    )
    assert first.status_code == 201

    init = api.post(
        "/api/v1/media/uploads", _init_body(len(body), filename="b.txt"), format="json",
    )
    upload_id = init.data["data"]["upload_id"]
    _put(init.data["data"]["presigned_url"], body, "text/plain")
    r = api.post(
        f"/api/v1/media/uploads/{upload_id}/complete", {"checksum": _sha256(body)}, format="json"
    )
    assert r.status_code == 409
    assert r.data["code"] == "DUPLICATE_FILE"


# --- MED-01 : multipart direct -------------------------------------------------


@pytest.mark.django_db
def test_direct_upload_ok(api, jean):
    _jwt(api, jean)
    r = api.post(
        "/api/v1/media/upload",
        {"file": SimpleUploadedFile("a.pdf", b"pdf-bytes", content_type="application/pdf")},
        format="multipart",
    )
    assert r.status_code == 201
    media_id = r.data["data"]["id"]
    media = MediaFile.objects.get(pk=media_id)
    assert storage.head_object(media.storage_path) is not None


@pytest.mark.django_db
def test_direct_upload_too_large(api, jean):
    _jwt(api, jean)
    big = b"x" * (10 * 1024 * 1024 + 1)
    r = api.post(
        "/api/v1/media/upload",
        {"file": SimpleUploadedFile("big.bin", big, content_type="application/octet-stream")},
        format="multipart",
    )
    assert r.status_code == 413
    assert r.data["code"] == "FILE_TOO_LARGE"


@pytest.mark.django_db
def test_direct_upload_duplicate(api, jean):
    _jwt(api, jean)
    body = b"same-bytes-twice"
    r1 = api.post(
        "/api/v1/media/upload",
        {"file": SimpleUploadedFile("a.txt", body, content_type="text/plain")},
        format="multipart",
    )
    assert r1.status_code == 201
    r2 = api.post(
        "/api/v1/media/upload",
        {"file": SimpleUploadedFile("b.txt", body, content_type="text/plain")},
        format="multipart",
    )
    assert r2.status_code == 409
    assert r2.data["code"] == "DUPLICATE_FILE"


# --- MED-09/10/11 ---------------------------------------------------------------


@pytest.mark.django_db
def test_get_metadata_owner_ok(api, jean):
    _jwt(api, jean)
    up = api.post(
        "/api/v1/media/upload",
        {"file": SimpleUploadedFile("a.pdf", b"abc", content_type="application/pdf")},
        format="multipart",
    )
    r = api.get(f"/api/v1/media/{up.data['data']['id']}")
    assert r.status_code == 200


@pytest.mark.django_db
def test_get_metadata_other_user_404(api, jean, marie):
    _jwt(api, jean)
    up = api.post(
        "/api/v1/media/upload",
        {"file": SimpleUploadedFile("a.pdf", b"abc", content_type="application/pdf")},
        format="multipart",
    )
    _jwt(api, marie)
    r = api.get(f"/api/v1/media/{up.data['data']['id']}")
    assert r.status_code == 404


@pytest.mark.django_db
def test_download_owner_redirects_and_logs(api, jean):
    _jwt(api, jean)
    up = api.post(
        "/api/v1/media/upload",
        {"file": SimpleUploadedFile("a.pdf", b"abc", content_type="application/pdf")},
        format="multipart",
    )
    media_id = up.data["data"]["id"]
    r = api.get(f"/api/v1/media/{media_id}/download")
    assert r.status_code == 302
    assert "Location" in r.headers
    assert MediaAccessLog.objects.filter(
        media_id=media_id, action=MediaAccessLog.Action.DOWNLOAD
    ).exists()


@pytest.mark.django_db
def test_download_infected_forbidden(api, jean):
    media = MediaFile.objects.create(
        owner=jean, storage_path="document/2026/x.pdf",
        media_type=MediaFile.MediaType.DOCUMENT, scan_status=MediaFile.ScanStatus.INFECTED,
    )
    _jwt(api, jean)
    r = api.get(f"/api/v1/media/{media.id}/download")
    assert r.status_code == 403
    assert r.data["code"] == "FILE_INFECTED"


@pytest.mark.django_db
def test_delete_owner_removes_object_and_quota(api, jean):
    _jwt(api, jean)
    body = b"delete-me-bytes"
    up = api.post(
        "/api/v1/media/upload",
        {"file": SimpleUploadedFile("a.txt", body, content_type="text/plain")},
        format="multipart",
    )
    media_id = up.data["data"]["id"]
    media = MediaFile.objects.get(pk=media_id)
    key = media.storage_path
    usage = StorageUsage.objects.get(user=jean, storage_type=StorageUsage.StorageType.PERSONAL)
    assert usage.used_bytes == len(body)

    r = api.delete(f"/api/v1/media/{media_id}")
    assert r.status_code == 204
    assert storage.head_object(key) is None
    usage.refresh_from_db()
    assert usage.used_bytes == 0


@pytest.mark.django_db
def test_delete_other_user_404(api, jean, marie):
    _jwt(api, jean)
    up = api.post(
        "/api/v1/media/upload",
        {"file": SimpleUploadedFile("a.pdf", b"abc", content_type="application/pdf")},
        format="multipart",
    )
    _jwt(api, marie)
    r = api.delete(f"/api/v1/media/{up.data['data']['id']}")
    assert r.status_code == 404


# --- Auth / permissions ---------------------------------------------------------


@pytest.mark.django_db
def test_without_permission_403(api, jean):
    RolePermission.objects.filter(role=jean.role, permission__code="media.file.upload").delete()
    invalidate_role_cache(jean.role_id)
    _jwt(api, jean)
    r = api.post(
        "/api/v1/media/upload",
        {"file": SimpleUploadedFile("a.pdf", b"abc", content_type="application/pdf")},
        format="multipart",
    )
    assert r.status_code == 403
    assert r.data["code"] == "FORBIDDEN"


@pytest.mark.django_db
def test_without_jwt_401(api, db):
    r = api.get("/api/v1/media/uploads")
    assert r.status_code == 401


@pytest.mark.django_db
def test_schema_has_media_a_paths(api, db):
    schema = api.get("/api/schema/")
    assert schema.status_code == 200
    text = schema.content.decode()
    assert "/api/v1/media/uploads" in text
    assert "/api/v1/media/{id}/download" in text or "/api/v1/media/{pk}/download" in text
