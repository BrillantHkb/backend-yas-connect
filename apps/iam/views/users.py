"""GET /api/v1/users (picker) + GET /api/v1/users/{id} — fiche collègue PROF-02."""

from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.iam.serializers.profile import ColleagueEnvelopeSerializer
from apps.iam.serializers.search import UserSearchEnvelopeSerializer
from apps.iam.services.profile_service import get_colleague, serialize_colleague
from apps.iam.services.search_service import search_users


class UserSearchView(APIView):
    required_permission = "iam.profile.read_other"

    @extend_schema(
        tags=["Users"],
        parameters=[
            OpenApiParameter("q", str, OpenApiParameter.QUERY, required=True),
            OpenApiParameter("region_id", str, OpenApiParameter.QUERY, required=False),
            OpenApiParameter("segment_id", str, OpenApiParameter.QUERY, required=False),
            OpenApiParameter("limit", int, OpenApiParameter.QUERY, required=False),
            OpenApiParameter("offset", int, OpenApiParameter.QUERY, required=False),
        ],
        responses={
            200: UserSearchEnvelopeSerializer,
            400: OpenApiResponse(description="QUERY_TOO_SHORT / VALIDATION_ERROR"),
        },
        description="People-picker : `q` obligatoire (2–64). Pas d’e-mail. Privacy 23–25 par hit.",
    )
    def get(self, request):
        data = search_users(request=request, viewer=request.user)
        return Response({"success": True, "data": data})


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
