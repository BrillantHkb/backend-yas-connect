"""GET + PATCH /api/v1/me/preferences — PROF-B. Après CGU + wizard."""

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.iam.models import User
from apps.iam.serializers.prefs import PreferencesBodySerializer, PreferencesEnvelopeSerializer
from apps.iam.services.auth_service import client_ip
from apps.iam.services.prefs_service import patch_preferences, serialize_preferences


class MePreferencesView(APIView):
    required_permissions = {
        "GET": "iam.prefs.read",
        "PATCH": "iam.prefs.update",
    }

    @extend_schema(
        tags=["Me"],
        responses={200: PreferencesEnvelopeSerializer},
        description="Préférences UI (langue, fuseau, son, DL, souhaits). Distinct de privacy.",
    )
    def get(self, request):
        user = User.objects.select_related("preferences").get(pk=request.user.pk)
        return Response({"success": True, "data": serialize_preferences(user)})

    @extend_schema(
        tags=["Me"],
        request=PreferencesBodySerializer,
        responses={
            200: PreferencesEnvelopeSerializer,
            400: OpenApiResponse(
                description="UNKNOWN_FIELD / INVALID_LANGUAGE / INVALID_TIMEZONE"
            ),
        },
    )
    def patch(self, request):
        data = patch_preferences(
            user=request.user,
            data=request.data or {},
            actor=request.user,
            ip=client_ip(request),
        )
        return Response({"success": True, "data": data})
