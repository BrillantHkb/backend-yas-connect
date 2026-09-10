"""D05 + AUTH-R09 : users admin. JWT + HasPermission (plus IsAdminRole)."""

from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.iam.serializers.rbac import UserRoleSerializer
from apps.iam.serializers.register import RejectUserSerializer
from apps.iam.serializers.security import (
    LoginHistoryEnvelopeSerializer,
    UnlockEnvelopeSerializer,
    UnlockSerializer,
)
from apps.iam.services.auth_service import client_ip
from apps.iam.services.lock_service import unlock_user
from apps.iam.services.mfa_service import admin_reset_mfa
from apps.iam.services.rbac_service import assign_user_role
from apps.iam.services.register_service import (
    approve_user,
    list_users,
    reject_user,
)
from apps.iam.services.security_service import get_user_or_404, list_logins, parse_login_query


class AdminUserListView(APIView):
    required_permission = "iam.user.read"

    @extend_schema(
        tags=["Admin"],
        parameters=[
            OpenApiParameter(
                name="pending",
                type=bool,
                location=OpenApiParameter.QUERY,
                required=False,
                description="true = file hors AD (pending_approval)",
            )
        ],
        responses={200: OpenApiResponse(description="Tous les users ; pending=true = file RH")},
    )
    def get(self, request):
        pending = str(request.query_params.get("pending", "")).lower() in ("1", "true", "yes")
        return Response({"success": True, "data": list_users(pending_only=pending)})


class AdminUserApproveView(APIView):
    required_permission = "iam.user.approve"

    @extend_schema(
        tags=["Admin"],
        responses={
            200: OpenApiResponse(description="Approuvé (idempotent si déjà actif)"),
            400: OpenApiResponse(description="LDAP_MANAGED"),
            404: OpenApiResponse(description="NOT_FOUND"),
        },
    )
    def post(self, request, pk):
        approve_user(user_id=pk, actor=request.user, ip=client_ip(request))
        return Response({"success": True, "data": {"approved": True}})


class AdminUserRejectView(APIView):
    required_permission = "iam.user.reject"

    @extend_schema(
        tags=["Admin"],
        request=RejectUserSerializer,
        responses={
            200: OpenApiResponse(description="Rejeté (reste inactif)"),
            400: OpenApiResponse(description="LDAP_MANAGED / VALIDATION"),
            404: OpenApiResponse(description="NOT_FOUND"),
        },
    )
    def post(self, request, pk):
        ser = RejectUserSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        reject_user(
            user_id=pk,
            reason=ser.validated_data["reason"],
            actor=request.user,
            ip=client_ip(request),
        )
        return Response({"success": True, "data": {"rejected": True}})


class AdminMfaResetView(APIView):
    """AUTH-24 : iam.mfa.reset."""

    required_permission = "iam.mfa.reset"

    @extend_schema(
        tags=["Admin"],
        responses={
            200: OpenApiResponse(description="otp_secrets supprimé ; sessions révoquées"),
            404: OpenApiResponse(description="NOT_FOUND"),
        },
    )
    def post(self, request, pk):
        admin_reset_mfa(user_id=pk, actor=request.user)
        return Response({"success": True, "data": {"reset": True}})


class AdminUserUnlockView(APIView):
    """POST /api/v1/admin/users/{id}/unlock — iam.user.unlock. 200 idempotent."""

    required_permission = "iam.user.unlock"

    @extend_schema(
        tags=["Admin"],
        request=UnlockSerializer,
        responses={
            200: UnlockEnvelopeSerializer,
            404: OpenApiResponse(description="NOT_FOUND"),
        },
    )
    def post(self, request, pk):
        ser = UnlockSerializer(data=request.data or {})
        ser.is_valid(raise_exception=True)
        target = get_user_or_404(pk)
        unlock_user(
            user=target,
            actor=request.user,
            ip=client_ip(request),
            reason=ser.validated_data.get("reason") or "",
        )
        return Response({"success": True, "data": {"unlocked": True}})


class AdminUserLoginsView(APIView):
    """GET /api/v1/admin/users/{id}/logins — iam.user_security.read."""

    required_permission = "iam.user_security.read"

    @extend_schema(
        tags=["Admin"],
        parameters=[
            OpenApiParameter(
                name="limit",
                type=int,
                location=OpenApiParameter.QUERY,
                required=False,
            ),
            OpenApiParameter(
                name="before",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
            ),
        ],
        responses={
            200: LoginHistoryEnvelopeSerializer,
            404: OpenApiResponse(description="NOT_FOUND"),
        },
    )
    def get(self, request, pk):
        target = get_user_or_404(pk)
        limit, before = parse_login_query(request)
        logins = list_logins(user=target, limit=limit, before=before)
        return Response({"success": True, "data": {"logins": logins}})


class AdminUserRoleView(APIView):
    """PATCH /api/v1/admin/users/{id}/role — iam.user.role_assign."""

    required_permission = "iam.user.role_assign"

    @extend_schema(
        tags=["Admin"],
        request=UserRoleSerializer,
        responses={
            200: OpenApiResponse(description="Rôle mis à jour"),
            404: OpenApiResponse(description="ROLE_NOT_FOUND / NOT_FOUND"),
            409: OpenApiResponse(description="LAST_ADMIN"),
        },
    )
    def patch(self, request, pk):
        ser = UserRoleSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        target = get_user_or_404(pk)
        data = assign_user_role(
            user=target,
            role_code=ser.validated_data["role_code"],
            actor=request.user,
            ip=client_ip(request),
        )
        return Response({"success": True, "data": data})
