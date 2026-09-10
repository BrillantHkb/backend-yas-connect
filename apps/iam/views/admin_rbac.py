"""AUTH-R : CRUD rôles, catalogue permissions, matrice. JWT + HasPermission."""

from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.iam.serializers.rbac import (
    PermissionCodesSerializer,
    PermissionCreateSerializer,
    RoleCreateSerializer,
    RolePatchSerializer,
)
from apps.iam.services.auth_service import client_ip
from apps.iam.services.rbac_service import (
    add_role_permissions,
    create_permission,
    create_role,
    delete_permission,
    delete_role,
    get_permission_or_404,
    get_role_or_404,
    list_permissions,
    list_roles,
    patch_role,
    remove_role_permissions,
    serialize_role,
    set_role_permissions,
)


class RoleListCreateView(APIView):
    required_permissions = {"GET": "iam.role.read", "POST": "iam.role.manage"}

    @extend_schema(
        tags=["Admin"],
        parameters=[
            OpenApiParameter("q", str, OpenApiParameter.QUERY, required=False),
            OpenApiParameter("is_system", bool, OpenApiParameter.QUERY, required=False),
            OpenApiParameter("limit", int, OpenApiParameter.QUERY, required=False),
            OpenApiParameter("offset", int, OpenApiParameter.QUERY, required=False),
        ],
        responses={200: OpenApiResponse(description="Liste rôles (sans permission_codes)")},
    )
    def get(self, request):
        return Response({"success": True, "data": list_roles(request)})

    @extend_schema(
        tags=["Admin"],
        request=RoleCreateSerializer,
        responses={
            201: OpenApiResponse(description="Rôle custom, perms vides"),
            400: OpenApiResponse(description="INVALID_ROLE_CODE / FIELD_FORBIDDEN"),
            409: OpenApiResponse(description="ROLE_CODE_TAKEN"),
        },
    )
    def post(self, request):
        data = create_role(data=request.data or {}, actor=request.user, ip=client_ip(request))
        return Response({"success": True, "data": data}, status=201)


class RoleDetailView(APIView):
    required_permissions = {
        "GET": "iam.role.read",
        "PATCH": "iam.role.manage",
        "DELETE": "iam.role.manage",
    }

    @extend_schema(tags=["Admin"], responses={200: OpenApiResponse(), 404: OpenApiResponse()})
    def get(self, request, pk):
        role = get_role_or_404(pk)
        return Response({"success": True, "data": serialize_role(role, with_codes=True)})

    @extend_schema(tags=["Admin"], request=RolePatchSerializer)
    def patch(self, request, pk):
        role = get_role_or_404(pk)
        data = patch_role(
            role=role, data=request.data or {}, actor=request.user, ip=client_ip(request)
        )
        return Response({"success": True, "data": data})

    @extend_schema(tags=["Admin"], responses={204: OpenApiResponse(), 409: OpenApiResponse()})
    def delete(self, request, pk):
        role = get_role_or_404(pk)
        delete_role(role=role, actor=request.user, ip=client_ip(request))
        return Response(status=204)


class RolePermissionsView(APIView):
    required_permissions = {
        "GET": "iam.role.read",
        "POST": "iam.role.grant",
        "DELETE": "iam.role.grant",
        "PUT": "iam.role.grant",
    }

    @extend_schema(tags=["Admin"])
    def get(self, request, pk):
        role = get_role_or_404(pk)
        return Response({"success": True, "data": serialize_role(role, with_codes=True)})

    @extend_schema(tags=["Admin"], request=PermissionCodesSerializer)
    def post(self, request, pk):
        role = get_role_or_404(pk)
        data = add_role_permissions(
            role=role, data=request.data or {}, actor=request.user, ip=client_ip(request)
        )
        return Response({"success": True, "data": data})

    @extend_schema(tags=["Admin"], request=PermissionCodesSerializer)
    def delete(self, request, pk):
        role = get_role_or_404(pk)
        data = remove_role_permissions(
            role=role, data=request.data or {}, actor=request.user, ip=client_ip(request)
        )
        return Response({"success": True, "data": data})

    @extend_schema(tags=["Admin"], request=PermissionCodesSerializer)
    def put(self, request, pk):
        role = get_role_or_404(pk)
        data = set_role_permissions(
            role=role, data=request.data or {}, actor=request.user, ip=client_ip(request)
        )
        return Response({"success": True, "data": data})


class PermissionListCreateView(APIView):
    required_permissions = {"GET": "iam.permission.read", "POST": "iam.permission.manage"}

    @extend_schema(
        tags=["Admin"],
        parameters=[OpenApiParameter("module", str, OpenApiParameter.QUERY, required=False)],
    )
    def get(self, request):
        return Response({"success": True, "data": list_permissions(request)})

    @extend_schema(tags=["Admin"], request=PermissionCreateSerializer)
    def post(self, request):
        data = create_permission(
            data=request.data or {}, actor=request.user, ip=client_ip(request)
        )
        return Response({"success": True, "data": data}, status=201)


class PermissionDeleteView(APIView):
    required_permission = "iam.permission.manage"

    @extend_schema(tags=["Admin"], responses={204: OpenApiResponse(), 409: OpenApiResponse()})
    def delete(self, request, pk):
        perm = get_permission_or_404(pk)
        delete_permission(perm=perm, actor=request.user, ip=client_ip(request))
        return Response(status=204)
