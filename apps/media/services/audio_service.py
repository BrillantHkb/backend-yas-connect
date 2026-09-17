"""MEDIA-D : transcription (stub synchrone), historique (MED-43…54)."""

from apps.iam.exceptions import AuthAPIError
from apps.iam.models import User
from apps.media.models import AudioMessage, VoiceTranscription
from apps.media.services.upload_service import get_own_media_or_404

MSG_NOT_FOUND = "Message vocal introuvable."


def _get_audio_or_404(user: User, pk) -> AudioMessage:
    media = get_own_media_or_404(user, pk)
    try:
        return media.audio_detail
    except AudioMessage.DoesNotExist as exc:
        raise AuthAPIError(404, "NOT_FOUND", MSG_NOT_FOUND) from exc


def transcribe(*, user: User, pk, language: str = "") -> VoiceTranscription:
    """Stub : PENDING→PROCESSING→DONE synchrone, nouvelle ligne à chaque appel (MED-53)."""
    audio = _get_audio_or_404(user, pk)
    audio.transcription_status = AudioMessage.TranscriptionStatus.PROCESSING
    audio.save(update_fields=["transcription_status"])

    transcription = VoiceTranscription.objects.create(
        audio=audio, language=(language or "fr").strip(), text="", model_used="stub"
    )
    audio.transcription_status = AudioMessage.TranscriptionStatus.DONE
    audio.save(update_fields=["transcription_status"])
    return transcription


def list_transcriptions(*, user: User, pk) -> dict:
    audio = _get_audio_or_404(user, pk)
    rows = audio.transcriptions.order_by("-created_at")
    return {
        "results": [
            {
                "id": str(r.id),
                "language": r.language,
                "text": r.text,
                "confidence": float(r.confidence) if r.confidence is not None else None,
                "model_used": r.model_used,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ]
    }
