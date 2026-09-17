"""MEDIA-D : transcription, historique."""

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.media.serializers.audio import TranscribeSerializer
from apps.media.services import audio_service


class MediaAudioTranscribeView(APIView):
    required_permission = "media.audio.manage"

    @extend_schema(tags=["Media"], request=TranscribeSerializer, responses={202: OpenApiResponse()})
    def post(self, request, pk):
        ser = TranscribeSerializer(data=request.data or {})
        ser.is_valid(raise_exception=True)
        transcription = audio_service.transcribe(
            user=request.user, pk=pk, language=ser.validated_data["language"]
        )
        return Response(
            {
                "success": True,
                "data": {"transcription_status": "DONE", "transcription_id": str(transcription.id)},
            },
            status=202,
        )


class MediaAudioTranscriptionsView(APIView):
    required_permission = "media.audio.manage"

    @extend_schema(tags=["Media"], responses={200: OpenApiResponse()})
    def get(self, request, pk):
        data = audio_service.list_transcriptions(user=request.user, pk=pk)
        return Response({"success": True, "data": data})
