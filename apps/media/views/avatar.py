"""POST/DELETE /api/v1/me/avatar — monté depuis urls/me.py."""

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.iam.exceptions import AuthAPIError
from apps.iam.models import User
from apps.iam.serializers.profile import AvatarEnvelopeSerializer
from apps.iam.services.auth_service import client_ip
from apps.media.services.avatar_service import clear_avatar, upload_avatar

MSG_INVALID = "Fichier image invalide."


class MeAvatarView(APIView):
    required_permission = "media.avatar.manage"
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(
        tags=["Me"],
        request={
            "multipart/form-data": {
                "type": "object",
                "properties": {"file": {"type": "string", "format": "binary"}},
            }
        },
        responses={
            200: AvatarEnvelopeSerializer,
            400: OpenApiResponse(description="INVALID_MEDIA / AVATAR_TOO_LARGE / MEDIA_INFECTED"),
        },
    )
    def post(self, request):
        uploaded = request.FILES.get("file")
        if not uploaded:
            raise AuthAPIError(400, "INVALID_MEDIA", MSG_INVALID)
        data = upload_avatar(
            user=request.user,
            uploaded=uploaded,
            actor=request.user,
            ip=client_ip(request),
        )
        return Response({"success": True, "data": data})

    @extend_schema(
        tags=["Me"],
        responses={200: OpenApiResponse(description="ok")},
    )
    def delete(self, request):
        user = User.objects.get(pk=request.user.pk)
        clear_avatar(user=user, actor=request.user, ip=client_ip(request))
        return Response({"success": True, "data": {"ok": True}})
