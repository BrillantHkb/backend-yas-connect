"""ANNUAIRE-B : CRUD admin segment_types / segments + arbre. Pas de porte CGU/wizard."""

from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.annuaire.serializers.admin_org import (
    SegmentCreateSerializer,
    SegmentPatchSerializer,
    SegmentTypeCreateSerializer,
    SegmentTypePatchSerializer,
)
from apps.annuaire.services.org_tree import (
    create_segment,
    create_segment_type,
    delete_segment,
    delete_segment_type,
    get_segment_detail,
    get_segment_or_404,
    get_segment_type_or_404,
    get_tree,
    list_segment_types,
    list_segments,
    patch_segment,
    patch_segment_type,
    serialize_segment_type,
)
from apps.iam.services.auth_service import client_ip


class AdminSegmentTypeListCreateView(APIView):
    required_permissions = {
        "GET": "annuaire.segment_type.read",
        "POST": "annuaire.segment_type.manage",
    }

    @extend_schema(
        tags=["Admin"],
        parameters=[
            OpenApiParameter("q", str, OpenApiParameter.QUERY, required=False),
            OpenApiParameter("is_active", bool, OpenApiParameter.QUERY, required=False),
            OpenApiParameter("limit", int, OpenApiParameter.QUERY, required=False),
            OpenApiParameter("offset", int, OpenApiParameter.QUERY, required=False),
        ],
        responses={200: OpenApiResponse(description="Types d’unité (admin voit inactifs)")},
    )
    def get(self, request):
        return Response({"success": True, "data": list_segment_types(request)})

    @extend_schema(
        tags=["Admin"],
        request=SegmentTypeCreateSerializer,
        responses={
            201: OpenApiResponse(description="Type créé"),
            409: OpenApiResponse(description="SEGMENT_TYPE_CODE_TAKEN / NAME_TAKEN"),
        },
    )
    def post(self, request):
        ser = SegmentTypeCreateSerializer(data=request.data or {})
        ser.is_valid(raise_exception=True)
        data = create_segment_type(
            data=ser.validated_data, actor=request.user, ip=client_ip(request)
        )
        return Response({"success": True, "data": data}, status=201)


class AdminSegmentTypeDetailView(APIView):
    required_permissions = {
        "GET": "annuaire.segment_type.read",
        "PATCH": "annuaire.segment_type.manage",
        "DELETE": "annuaire.segment_type.manage",
    }

    @extend_schema(tags=["Admin"], responses={200: OpenApiResponse(), 404: OpenApiResponse()})
    def get(self, request, pk):
        st = get_segment_type_or_404(pk)
        return Response({"success": True, "data": serialize_segment_type(st)})

    @extend_schema(
        tags=["Admin"],
        request=SegmentTypePatchSerializer,
        responses={200: OpenApiResponse(), 400: OpenApiResponse(description="CODE_IMMUTABLE")},
    )
    def patch(self, request, pk):
        st = get_segment_type_or_404(pk)
        data = patch_segment_type(
            segment_type=st, data=request.data or {}, actor=request.user, ip=client_ip(request)
        )
        return Response({"success": True, "data": data})

    @extend_schema(
        tags=["Admin"],
        responses={
            204: OpenApiResponse(),
            409: OpenApiResponse(description="TYPE_SYSTEM / TYPE_IN_USE"),
        },
    )
    def delete(self, request, pk):
        st = get_segment_type_or_404(pk)
        delete_segment_type(segment_type=st, actor=request.user, ip=client_ip(request))
        return Response(status=204)


class AdminSegmentListCreateView(APIView):
    required_permissions = {
        "GET": "annuaire.segment.read",
        "POST": "annuaire.segment.manage",
    }

    @extend_schema(
        tags=["Admin"],
        parameters=[
            OpenApiParameter("q", str, OpenApiParameter.QUERY, required=False),
            OpenApiParameter("parent_id", str, OpenApiParameter.QUERY, required=False),
            OpenApiParameter("type_id", str, OpenApiParameter.QUERY, required=False),
            OpenApiParameter("is_active", bool, OpenApiParameter.QUERY, required=False),
            OpenApiParameter("limit", int, OpenApiParameter.QUERY, required=False),
            OpenApiParameter("offset", int, OpenApiParameter.QUERY, required=False),
        ],
        responses={200: OpenApiResponse(description="Segments (admin voit inactifs)")},
    )
    def get(self, request):
        return Response({"success": True, "data": list_segments(request)})

    @extend_schema(
        tags=["Admin"],
        request=SegmentCreateSerializer,
        responses={
            201: OpenApiResponse(description="Segment créé"),
            400: OpenApiResponse(
                description="SEGMENT_LEVEL_INVALID / SEGMENT_INVALID / TYPE_INVALID / "
                "RESPONSABLE_INVALID"
            ),
            409: OpenApiResponse(description="SEGMENT_CODE_TAKEN"),
        },
    )
    def post(self, request):
        ser = SegmentCreateSerializer(data=request.data or {})
        ser.is_valid(raise_exception=True)
        data = create_segment(data=ser.validated_data, actor=request.user, ip=client_ip(request))
        return Response({"success": True, "data": data}, status=201)


class AdminSegmentDetailView(APIView):
    required_permissions = {
        "GET": "annuaire.segment.read",
        "PATCH": "annuaire.segment.manage",
        "DELETE": "annuaire.segment.manage",
    }

    @extend_schema(tags=["Admin"], responses={200: OpenApiResponse(), 404: OpenApiResponse()})
    def get(self, request, pk):
        return Response({"success": True, "data": get_segment_detail(pk)})

    @extend_schema(
        tags=["Admin"],
        request=SegmentPatchSerializer,
        responses={
            200: OpenApiResponse(),
            400: OpenApiResponse(description="SEGMENT_CYCLE / SEGMENT_PARENT_SELF / …"),
            409: OpenApiResponse(description="SEGMENT_CODE_TAKEN"),
        },
    )
    def patch(self, request, pk):
        segment = get_segment_or_404(pk)
        data = patch_segment(
            segment=segment, data=request.data or {}, actor=request.user, ip=client_ip(request)
        )
        return Response({"success": True, "data": data})

    @extend_schema(
        tags=["Admin"],
        responses={204: OpenApiResponse(), 409: OpenApiResponse(description="SEGMENT_IN_USE")},
    )
    def delete(self, request, pk):
        segment = get_segment_or_404(pk)
        delete_segment(segment=segment, actor=request.user, ip=client_ip(request))
        return Response(status=204)


class AdminSegmentTreeView(APIView):
    required_permission = "annuaire.segment.read"

    @extend_schema(
        tags=["Admin"],
        parameters=[
            OpenApiParameter("root_id", str, OpenApiParameter.QUERY, required=False),
            OpenApiParameter("include_inactive", bool, OpenApiParameter.QUERY, required=False),
        ],
        responses={200: OpenApiResponse(description="Arbre imbriqué (children[])")},
    )
    def get(self, request):
        return Response({"success": True, "data": get_tree(request)})
