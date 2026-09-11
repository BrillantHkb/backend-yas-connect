"""GET + PATCH /api/v1/me — fiche PROF-A + gates AUTH-F."""

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.iam.models import User
from apps.iam.serializers.compliance import MeEnvelopeSerializer
from apps.iam.serializers.profile import ProfilePatchSerializer
from apps.iam.services.auth_service import client_ip
from apps.iam.services.compliance_service import gates_payload
from apps.iam.services.profile_service import patch_profile, serialize_me


class MeView(APIView):
    """GET allowlist TOS ; PATCH après CGU + wizard."""

    required_permissions = {
        "GET": "iam.profile.read",
        "PATCH": "iam.profile.update",
    }

    @extend_schema(
        tags=["Me"],
        responses={200: MeEnvelopeSerializer},
        description=(
            "Fiche JWT + portes CGU / wizard. Toujours 200 si session OK "
            "(même si tos_required / onboarding_required). Pas de rôle (claim JWT)."
        ),
    )
    def get(self, request):
        user = User.objects.select_related("region", "preferences", "privacy").get(
            pk=request.user.pk
        )
        return Response(
            {
                "success": True,
                "data": {
                    "user": serialize_me(user),
                    "gates": gates_payload(user),
                },
            }
        )

    @extend_schema(
        tags=["Me"],
        request=ProfilePatchSerializer,
        responses={
            200: MeEnvelopeSerializer,
            400: OpenApiResponse(description="FIELD_FORBIDDEN / VALIDATION_ERROR"),
            409: OpenApiResponse(description="USERNAME_TAKEN"),
        },
    )
    def patch(self, request):
        user = patch_profile(
            user=request.user,
            data=request.data or {},
            actor=request.user,
            ip=client_ip(request),
        )
        user = User.objects.select_related("region", "preferences", "privacy").get(pk=user.pk)
        return Response(
            {
                "success": True,
                "data": {
                    "user": serialize_me(user),
                    "gates": gates_payload(user),
                },
            }
        )
