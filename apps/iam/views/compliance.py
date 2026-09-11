"""AUTH-F : CGU + wizard. JWT + iam.tos.manage / iam.onboarding.manage."""

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.iam.serializers.compliance import (
    OnboardingEnvelopeSerializer,
    OnboardingPatchSerializer,
    TosAcceptSerializer,
    TosEnvelopeSerializer,
)
from apps.iam.services.compliance_service import (
    accept_tos,
    complete_onboarding,
    onboarding_payload,
    patch_onboarding,
    tos_public,
)


class TosView(APIView):
    """GET /api/v1/me/tos — version + URL courantes."""

    required_permission = "iam.tos.manage"

    @extend_schema(
        tags=["Me"],
        responses={200: TosEnvelopeSerializer},
        description="CGU en vigueur (texte = URL, pas un PDF en base).",
    )
    def get(self, request):
        return Response({"success": True, "data": tos_public()})


class TosAcceptView(APIView):
    """POST /api/v1/me/tos/accept — body { version }."""

    required_permission = "iam.tos.manage"

    @extend_schema(
        tags=["Me"],
        request=TosAcceptSerializer,
        responses={
            200: TosEnvelopeSerializer,
            409: OpenApiResponse(description="TOS_VERSION_MISMATCH"),
        },
        description="Écrit tos_accepted_at + tos_version. 409 si version ≠ courante.",
    )
    def post(self, request):
        ser = TosAcceptSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        accept_tos(user=request.user, version=ser.validated_data["version"])
        return Response({"success": True, "data": tos_public()})


class OnboardingView(APIView):
    """GET + PATCH /api/v1/me/onboarding — prefs, pas onboarding_completed_at."""

    required_permission = "iam.onboarding.manage"

    @extend_schema(
        tags=["Me"],
        responses={200: OnboardingEnvelopeSerializer},
        description="Prérempli depuis user_preferences (même JSON que GET /me/preferences).",
    )
    def get(self, request):
        return Response({"success": True, "data": onboarding_payload(request.user)})

    @extend_schema(
        tags=["Me"],
        request=OnboardingPatchSerializer,
        responses={200: OnboardingEnvelopeSerializer},
        description="Écrit user_preferences et users.language/timezone. Ne termine pas le wizard.",
    )
    def patch(self, request):
        ser = OnboardingPatchSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = patch_onboarding(
            user=request.user,
            language=ser.validated_data.get("language"),
            timezone_name=ser.validated_data.get("timezone"),
            notification_sound=ser.validated_data.get("notification_sound"),
        )
        return Response({"success": True, "data": data})


class OnboardingCompleteView(APIView):
    """POST /api/v1/me/onboarding/complete — body vide. Exige CGU."""

    required_permission = "iam.onboarding.manage"

    @extend_schema(
        tags=["Me"],
        request=None,
        responses={
            200: OnboardingEnvelopeSerializer,
            403: OpenApiResponse(description="TOS_REQUIRED"),
        },
        description="Pose onboarding_completed_at. Audit ONBOARDING_COMPLETE.",
    )
    def post(self, request):
        complete_onboarding(user=request.user)
        return Response({"success": True, "data": onboarding_payload(request.user)})
