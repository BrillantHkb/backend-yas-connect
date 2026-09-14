"""GET + PATCH /api/v1/me/privacy — PROF-C. Après CGU + wizard."""

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.iam.models import User
from apps.iam.serializers.privacy import PrivacyBodySerializer, PrivacyEnvelopeSerializer
from apps.iam.services.auth_service import client_ip
from apps.iam.services.privacy_service import patch_privacy, serialize_privacy


class MePrivacyView(APIView):
    required_permissions = {
        "GET": "iam.privacy.read",
        "PATCH": "iam.privacy.update",
    }

    @extend_schema(
        tags=["Me"],
        responses={200: PrivacyEnvelopeSerializer},
        description="Confidentialité (visibilités + allow_*). Distinct des souhaits /me/preferences.",
    )
    def get(self, request):
        user = User.objects.select_related("privacy").get(pk=request.user.pk)
        return Response({"success": True, "data": serialize_privacy(user)})

    @extend_schema(
        tags=["Me"],
        request=PrivacyBodySerializer,
        responses={
            200: PrivacyEnvelopeSerializer,
            400: OpenApiResponse(
                description="UNKNOWN_FIELD / INVALID_VISIBILITY / VALIDATION_ERROR"
            ),
        },
    )
    def patch(self, request):
        data = patch_privacy(
            user=request.user,
            data=request.data or {},
            actor=request.user,
            ip=client_ip(request),
        )
        return Response({"success": True, "data": data})
