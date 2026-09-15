"""ANNUAIRE-C : CRUD admin historique affectations (user_segments). Pas de porte CGU/wizard."""

from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.annuaire.serializers.admin_assignments import (
    AssignmentCreateSerializer,
    AssignmentPatchSerializer,
)
from apps.annuaire.services.assignment import (
    create_assignment,
    delete_assignment,
    get_target_user_or_404,
    get_user_segment_or_404,
    list_assignments,
    patch_assignment,
    serialize_assignment,
)
from apps.iam.services.auth_service import client_ip


class AdminUserSegmentListCreateView(APIView):
    required_permissions = {
        "GET": "annuaire.user_segment.read",
        "POST": "annuaire.user_segment.manage",
    }

    @extend_schema(
        tags=["Admin"],
        parameters=[
            OpenApiParameter("include_closed", bool, OpenApiParameter.QUERY, required=False),
        ],
        responses={
            200: OpenApiResponse(description="Historique d’affectations"),
            404: OpenApiResponse(),
        },
    )
    def get(self, request, user_id):
        user = get_target_user_or_404(user_id)
        return Response({"success": True, "data": list_assignments(user, request)})

    @extend_schema(
        tags=["Admin"],
        request=AssignmentCreateSerializer,
        responses={
            201: OpenApiResponse(description="Affectation créée"),
            400: OpenApiResponse(description="SEGMENT_INVALID / ASSIGNMENT_DATE_INVALID"),
        },
    )
    def post(self, request, user_id):
        user = get_target_user_or_404(user_id)
        ser = AssignmentCreateSerializer(data=request.data or {})
        ser.is_valid(raise_exception=True)
        data = create_assignment(
            user=user, data=ser.validated_data, actor=request.user, ip=client_ip(request)
        )
        return Response({"success": True, "data": data}, status=201)


class AdminUserSegmentDetailView(APIView):
    required_permissions = {
        "GET": "annuaire.user_segment.read",
        "PATCH": "annuaire.user_segment.manage",
        "DELETE": "annuaire.user_segment.manage",
    }

    @extend_schema(tags=["Admin"], responses={200: OpenApiResponse(), 404: OpenApiResponse()})
    def get(self, request, pk):
        row = get_user_segment_or_404(pk)
        return Response({"success": True, "data": serialize_assignment(row)})

    @extend_schema(
        tags=["Admin"],
        request=AssignmentPatchSerializer,
        responses={
            200: OpenApiResponse(),
            400: OpenApiResponse(description="ASSIGNMENT_DATE_INVALID"),
        },
    )
    def patch(self, request, pk):
        row = get_user_segment_or_404(pk)
        data = patch_assignment(
            row=row, data=request.data or {}, actor=request.user, ip=client_ip(request)
        )
        return Response({"success": True, "data": data})

    @extend_schema(tags=["Admin"], responses={204: OpenApiResponse()})
    def delete(self, request, pk):
        row = get_user_segment_or_404(pk)
        delete_assignment(row=row, actor=request.user, ip=client_ip(request))
        return Response(status=204)
