"""ADMIN-A : CRUD régions. JWT + HasPermission. Seed 5 TG déjà seed_iam."""

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.iam.serializers.admin_users import RegionCreateSerializer, RegionPatchSerializer
from apps.iam.services.auth_service import client_ip
from apps.iam.services.region_service import (
    create_region,
    delete_region,
    get_region_detail,
    get_region_or_404,
    list_regions,
    patch_region,
)


class AdminRegionListCreateView(APIView):
    required_permissions = {"GET": "iam.region.read", "POST": "iam.region.manage"}

    @extend_schema(tags=["Admin"], responses={200: OpenApiResponse(description="Régions")})
    def get(self, request):
        return Response({"success": True, "data": list_regions()})

    @extend_schema(
        tags=["Admin"],
        request=RegionCreateSerializer,
        responses={
            201: OpenApiResponse(description="Région créée"),
            400: OpenApiResponse(description="VALIDATION_ERROR"),
            409: OpenApiResponse(description="REGION_CODE_TAKEN"),
        },
    )
    def post(self, request):
        ser = RegionCreateSerializer(data=request.data or {})
        ser.is_valid(raise_exception=True)
        data = create_region(data=ser.validated_data, actor=request.user, ip=client_ip(request))
        return Response({"success": True, "data": data}, status=201)


class AdminRegionDetailView(APIView):
    required_permissions = {
        "GET": "iam.region.read",
        "PATCH": "iam.region.manage",
        "DELETE": "iam.region.manage",
    }

    @extend_schema(tags=["Admin"], responses={200: OpenApiResponse(), 404: OpenApiResponse()})
    def get(self, request, pk):
        return Response({"success": True, "data": get_region_detail(pk)})

    @extend_schema(
        tags=["Admin"],
        request=RegionPatchSerializer,
        responses={
            200: OpenApiResponse(),
            400: OpenApiResponse(description="CODE_IMMUTABLE"),
            409: OpenApiResponse(description="REGION_NAME_TAKEN"),
        },
    )
    def patch(self, request, pk):
        region = get_region_or_404(pk)
        data = patch_region(
            region=region, data=request.data or {}, actor=request.user, ip=client_ip(request)
        )
        return Response({"success": True, "data": data})

    @extend_schema(
        tags=["Admin"],
        responses={
            204: OpenApiResponse(),
            409: OpenApiResponse(description="REGION_IN_USE"),
        },
    )
    def delete(self, request, pk):
        region = get_region_or_404(pk)
        delete_region(region=region, actor=request.user, ip=client_ip(request))
        return Response(status=204)
