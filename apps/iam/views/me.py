"""GET /api/v1/me — profil public + gates AUTH-F. Toujours 200 si JWT OK."""

from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.iam.models import User
from apps.iam.serializers.compliance import MeEnvelopeSerializer
from apps.iam.services.auth_service import public_user
from apps.iam.services.compliance_service import gates_payload


class MeView(APIView):
    """GET /api/v1/me — pas PROF-A (avatar / display_name plus tard)."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Me"],
        responses={200: MeEnvelopeSerializer},
        description=(
            "Profil JWT + portes CGU / wizard. Toujours 200 si session OK "
            "(même si tos_required / onboarding_required)."
        ),
    )
    def get(self, request):
        user = User.objects.select_related("role", "preferences", "privacy").get(pk=request.user.pk)
        return Response(
            {
                "success": True,
                "data": {
                    "user": public_user(user),
                    "gates": gates_payload(user),
                },
            }
        )
