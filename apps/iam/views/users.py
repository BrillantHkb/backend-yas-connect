"""GET /api/v1/users/{id} — fiche collègue PROF-02."""

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.iam.serializers.profile import ColleagueEnvelopeSerializer
from apps.iam.services.profile_service import get_colleague, serialize_colleague


class UserPublicView(APIView):
    required_permission = "iam.profile.read_other"

    @extend_schema(
        tags=["Users"],
        responses={
            200: ColleagueEnvelopeSerializer,
            400: OpenApiResponse(description="USE_ME"),
            404: OpenApiResponse(description="NOT_FOUND"),
        },
        description="Fiche d’un collègue (privacy du cible). Self → 400. Inactif / pending → 404.",
    )
    def get(self, request, pk):
        target = get_colleague(pk=pk, viewer=request.user)
        return Response(
            {
                "success": True,
                "data": {"user": serialize_colleague(target=target, viewer=request.user)},
            }
        )
