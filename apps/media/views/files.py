"""GET /api/v1/media/files/{id} — blob CLEAN/SKIPPED. Pas de privacy URL directe."""

from django.http import FileResponse
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.views import APIView

from apps.media.services.avatar_service import get_visible_media, media_abs_path


class MediaFileView(APIView):
    required_permission = "iam.profile.read"

    @extend_schema(
        tags=["Media"],
        responses={
            200: OpenApiResponse(description="Fichier binaire"),
            404: OpenApiResponse(description="NOT_FOUND"),
        },
    )
    def get(self, request, pk):
        media = get_visible_media(pk)
        path = media_abs_path(media)
        return FileResponse(
            path.open("rb"),
            content_type=media.mime_type or "application/octet-stream",
        )
