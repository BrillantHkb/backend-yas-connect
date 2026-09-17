"""MEDIA-C : vidéos (transcodage stub, stream, miniature)."""

import pytest
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from apps.iam.helpers.compliance import close_gates
from apps.iam.helpers.mfa import login_until_jwt
from apps.iam.models import Role, User
from apps.media.models import Video

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


def _jwt(api, user, *, password=PASSWORD, device_uuid="web-1"):
    device = {"device_uuid": device_uuid, "platform": "WEB"}
    r = login_until_jwt(api, email=user.email, password=password, device=device)
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {r.data['data']['access_token']}")
    return r


def _upload_video(api, body=b"fake-mp4-bytes"):
    r = api.post(
        "/api/v1/media/upload",
        {"file": SimpleUploadedFile("clip.mp4", body, content_type="video/mp4")},
        format="multipart",
    )
    assert r.status_code == 201, r.data
    return r.data["data"]["id"]


@pytest.mark.django_db
def test_direct_upload_video_creates_pending_video_row(api, jean):
    _jwt(api, jean)
    media_id = _upload_video(api)
    video = Video.objects.get(media_id=media_id)
    assert video.transcoding_status == Video.TranscodingStatus.PENDING
    assert video.streaming_ready is False


@pytest.mark.django_db
def test_stream_before_transcode_409(api, jean):
    _jwt(api, jean)
    media_id = _upload_video(api)
    r = api.get(f"/api/v1/media/{media_id}/video/stream")
    assert r.status_code == 409
    assert r.data["code"] == "VIDEO_NOT_READY"


@pytest.mark.django_db
def test_transcode_then_stream_ok(api, jean):
    _jwt(api, jean)
    media_id = _upload_video(api)
    r = api.post(f"/api/v1/media/{media_id}/video/transcode")
    assert r.status_code == 202
    assert r.data["data"]["transcoding_status"] == "READY"
    video = Video.objects.get(media_id=media_id)
    assert video.streaming_ready is True

    stream = api.get(f"/api/v1/media/{media_id}/video/stream")
    assert stream.status_code == 200
    assert stream.data["data"]["stream_url"]


@pytest.mark.django_db
def test_thumbnail_after_transcode_redirects(api, jean):
    _jwt(api, jean)
    media_id = _upload_video(api)
    api.post(f"/api/v1/media/{media_id}/video/transcode")
    r = api.get(f"/api/v1/media/{media_id}/video/thumbnail")
    assert r.status_code == 302
    assert "Location" in r.headers


@pytest.mark.django_db
def test_video_routes_on_non_video_404(api, jean):
    _jwt(api, jean)
    r = api.post(
        "/api/v1/media/upload",
        {"file": SimpleUploadedFile("a.pdf", b"pdf-bytes", content_type="application/pdf")},
        format="multipart",
    )
    media_id = r.data["data"]["id"]
    resp = api.post(f"/api/v1/media/{media_id}/video/transcode")
    assert resp.status_code == 404


@pytest.mark.django_db
def test_schema_has_video_stream_path(api, db):
    schema = api.get("/api/schema/")
    assert schema.status_code == 200
    assert "video/stream" in schema.content.decode()
