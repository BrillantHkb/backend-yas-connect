"""D05 : liste users + file pending + approve / reject. JWT + rôle ADMIN."""

from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.iam.permissions import IsAdminRole
from apps.iam.serializers_register import RejectUserSerializer
from apps.iam.services.auth_service import client_ip
from apps.iam.services.mfa_service import admin_reset_mfa
from apps.iam.services.register_service import (
    approve_user,
    list_users,
    reject_user,
)


class AdminUserListView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]

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
    permission_classes = [IsAuthenticated, IsAdminRole]

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
    permission_classes = [IsAuthenticated, IsAdminRole]

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
    """AUTH-24 : jour 4 = rôle ADMIN. AUTH-R → iam.mfa.reset."""

    permission_classes = [IsAuthenticated, IsAdminRole]

    @extend_schema(
        tags=["Admin"],
        responses={
            200: OpenApiResponse(description="otp_secrets supprimé ; sessions révoquées"),
            404: OpenApiResponse(description="NOT_FOUND"),
        },
    )
    def post(self, request, pk):
        admin_reset_mfa(user_id=pk, actor=request.user)  # delete otp_secrets + kill sessions
        return Response({"success": True, "data": {"reset": True}})
