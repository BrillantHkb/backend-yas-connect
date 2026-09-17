"""MEDIA-B : images (variantes stub, annotation/flou, dérivé, download ?variant=)."""

import hashlib
import urllib.request

import pytest
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from apps.iam.helpers.compliance import close_gates
from apps.iam.helpers.mfa import login_until_jwt
from apps.iam.models import Role, User
from apps.media.models import Image, MediaMetadata

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


def _upload_image(api, name="a.png", body=b"fake-png-bytes"):
    r = api.post(
        "/api/v1/media/upload",
        {"file": SimpleUploadedFile(name, body, content_type="image/png")},
        format="multipart",
    )
    assert r.status_code == 201, r.data
    return r.data["data"]["id"]


# --- Delta upload : création Image au complete/direct -----------------------------


@pytest.mark.django_db
def test_direct_upload_image_creates_image_row(api, jean):
    _jwt(api, jean)
    media_id = _upload_image(api)
    assert Image.objects.filter(media_id=media_id).exists()


@pytest.mark.django_db
def test_presigned_complete_with_metadata_creates_metadata_row(api, jean):
    _jwt(api, jean)
    body = b"fake-png-bytes-2"
    init = api.post(
        "/api/v1/media/uploads",
        {
            "filename": "b.png", "mime_type": "image/png",
            "size_bytes": len(body), "media_type": "IMAGE",
        },
        format="json",
    )
    upload_id = init.data["data"]["upload_id"]
    req = urllib.request.Request(
        init.data["data"]["presigned_url"], data=body, method="PUT",
        headers={"Content-Type": "image/png"},
    )
    urllib.request.urlopen(req, timeout=10).close()

    r = api.post(
        f"/api/v1/media/uploads/{upload_id}/complete",
        {
            "checksum": hashlib.sha256(body).hexdigest(),
            "metadata": {"width": 1920, "height": 1080, "device_model": "Pixel 8"},
        },
        format="json",
    )
    assert r.status_code == 200
    assert r.data["data"]["detail"]["format"] == "png"
    meta = MediaMetadata.objects.get(media_id=upload_id)
    assert meta.width == 1920
    assert meta.height == 1080
    assert meta.device_model == "Pixel 8"


# --- MED-25/26 : PATCH image --------------------------------------------------------


@pytest.mark.django_db
def test_patch_image_annotated(api, jean):
    _jwt(api, jean)
    media_id = _upload_image(api)
    r = api.patch(f"/api/v1/media/{media_id}/image", {"annotated": True}, format="json")
    assert r.status_code == 200
    assert r.data["data"]["annotated"] is True
    assert Image.objects.get(media_id=media_id).annotated is True


@pytest.mark.django_db
def test_patch_image_derivative_own_upload(api, jean):
    _jwt(api, jean)
    media_id = _upload_image(api)
    derivative_id = _upload_image(api, name="derivative.png", body=b"derivative-bytes")
    r = api.patch(
        f"/api/v1/media/{media_id}/image", {"derivative_upload_id": derivative_id}, format="json"
    )
    assert r.status_code == 200
    image = Image.objects.get(media_id=media_id)
    derivative = Image.objects.get(media_id=derivative_id).media
    assert image.optimized_path == derivative.storage_path


@pytest.mark.django_db
def test_patch_image_derivative_other_user_404(api, jean, marie):
    _jwt(api, jean)
    media_id = _upload_image(api)
    _jwt(api, marie)
    other_id = _upload_image(api, name="marie.png", body=b"marie-bytes")
    _jwt(api, jean)
    r = api.patch(
        f"/api/v1/media/{media_id}/image", {"derivative_upload_id": other_id}, format="json"
    )
    assert r.status_code == 404


# --- MED-21 : optimize ---------------------------------------------------------------


@pytest.mark.django_db
def test_optimize_idempotent(api, jean):
    _jwt(api, jean)
    media_id = _upload_image(api)
    r1 = api.post(f"/api/v1/media/{media_id}/image/optimize")
    assert r1.status_code == 202
    r2 = api.post(f"/api/v1/media/{media_id}/image/optimize")
    assert r2.status_code == 202


# --- MED-31 : download ?variant= -----------------------------------------------------


@pytest.mark.django_db
def test_download_variant_thumbnail(api, jean):
    _jwt(api, jean)
    media_id = _upload_image(api)
    r = api.get(f"/api/v1/media/{media_id}/download?variant=thumbnail")
    assert r.status_code == 302
    assert "Location" in r.headers


@pytest.mark.django_db
def test_download_variant_invalid_400(api, jean):
    _jwt(api, jean)
    media_id = _upload_image(api)
    r = api.get(f"/api/v1/media/{media_id}/download?variant=nope")
    assert r.status_code == 400
    assert r.data["code"] == "VALIDATION_ERROR"


@pytest.mark.django_db
def test_download_variant_thumbnail_without_image_404(api, jean):
    _jwt(api, jean)
    r = api.post(
        "/api/v1/media/upload",
        {"file": SimpleUploadedFile("a.pdf", b"pdf-bytes", content_type="application/pdf")},
        format="multipart",
    )
    media_id = r.data["data"]["id"]
    r = api.get(f"/api/v1/media/{media_id}/download?variant=thumbnail")
    assert r.status_code == 404


@pytest.mark.django_db
def test_schema_has_media_image_paths(api, db):
    schema = api.get("/api/schema/")
    assert schema.status_code == 200
    assert "image/optimize" in schema.content.decode()
