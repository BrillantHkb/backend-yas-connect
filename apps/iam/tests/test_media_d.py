"""MEDIA-D : audio (message vocal, transcription stub, historique)."""

import pytest
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from apps.iam.helpers.compliance import close_gates
from apps.iam.helpers.mfa import login_until_jwt
from apps.iam.models import Role, User
from apps.media.models import AudioMessage, VoiceTranscription

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


def _upload_audio(api, body=b"fake-opus-bytes"):
    r = api.post(
        "/api/v1/media/upload",
        {"file": SimpleUploadedFile("vocal.ogg", body, content_type="audio/ogg")},
        format="multipart",
    )
    assert r.status_code == 201, r.data
    return r.data["data"]["id"]


@pytest.mark.django_db
def test_direct_upload_audio_creates_pending_row(api, jean):
    _jwt(api, jean)
    media_id = _upload_audio(api)
    audio = AudioMessage.objects.get(media_id=media_id)
    assert audio.transcription_status == AudioMessage.TranscriptionStatus.PENDING


@pytest.mark.django_db
def test_transcribe_creates_transcription_and_marks_done(api, jean):
    _jwt(api, jean)
    media_id = _upload_audio(api)
    r = api.post(f"/api/v1/media/{media_id}/audio/transcribe", {"language": "en"}, format="json")
    assert r.status_code == 202
    assert r.data["data"]["transcription_status"] == "DONE"
    audio = AudioMessage.objects.get(media_id=media_id)
    assert audio.transcription_status == AudioMessage.TranscriptionStatus.DONE
    transcription = VoiceTranscription.objects.get(pk=r.data["data"]["transcription_id"])
    assert transcription.language == "en"
    assert transcription.model_used == "stub"


@pytest.mark.django_db
def test_transcribe_twice_keeps_history(api, jean):
    _jwt(api, jean)
    media_id = _upload_audio(api)
    api.post(f"/api/v1/media/{media_id}/audio/transcribe", {}, format="json")
    api.post(f"/api/v1/media/{media_id}/audio/transcribe", {}, format="json")
    audio = AudioMessage.objects.get(media_id=media_id)
    assert VoiceTranscription.objects.filter(audio=audio).count() == 2


@pytest.mark.django_db
def test_list_transcriptions(api, jean):
    _jwt(api, jean)
    media_id = _upload_audio(api)
    api.post(f"/api/v1/media/{media_id}/audio/transcribe", {}, format="json")
    api.post(f"/api/v1/media/{media_id}/audio/transcribe", {"language": "fr"}, format="json")
    r = api.get(f"/api/v1/media/{media_id}/audio/transcriptions")
    assert r.status_code == 200
    assert len(r.data["data"]["results"]) == 2


@pytest.mark.django_db
def test_schema_has_audio_transcribe_path(api, db):
    schema = api.get("/api/schema/")
    assert schema.status_code == 200
    assert "audio/transcribe" in schema.content.decode()
