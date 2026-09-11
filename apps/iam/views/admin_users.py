"""D05 + AUTH-R09 + ADMIN-A : users admin. JWT + HasPermission (plus IsAdminRole)."""

from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.iam.serializers.admin_users import (
    AdminPasswordSerializer,
    AdminReasonSerializer,
    AdminUserCreateSerializer,
)
from apps.iam.serializers.rbac import UserRoleSerializer
from apps.iam.serializers.register import RejectUserSerializer
from apps.iam.serializers.security import (
    LoginHistoryEnvelopeSerializer,
    UnlockEnvelopeSerializer,
    UnlockSerializer,
)
from apps.iam.services.admin_user_service import (
    create_local_user,
    disable_user,
    enable_user,
    get_user_detail,
    list_users,
    reset_user_password,
    revoke_all_sessions,
)
from apps.iam.services.auth_service import client_ip
from apps.iam.services.lock_service import unlock_user
from apps.iam.services.mfa_service import admin_reset_mfa
from apps.iam.services.rbac_service import assign_user_role
from apps.iam.services.register_service import approve_user, reject_user
from apps.iam.services.security_service import get_user_or_404, list_logins, parse_login_query


class AdminUserListView(APIView):
    required_permissions = {"GET": "iam.user.read", "POST": "iam.user.create"}

    @extend_schema(
        tags=["Admin"],
        parameters=[
            OpenApiParameter("q", str, OpenApiParameter.QUERY, required=False),
            OpenApiParameter(
                name="pending",
                type=bool,
                location=OpenApiParameter.QUERY,
                required=False,
                description="true = file hors AD (pending_approval)",
            ),
            OpenApiParameter("is_active", bool, OpenApiParameter.QUERY, required=False),
            OpenApiParameter("is_locked", bool, OpenApiParameter.QUERY, required=False),
            OpenApiParameter("role_code", str, OpenApiParameter.QUERY, required=False),
            OpenApiParameter("region_id", str, OpenApiParameter.QUERY, required=False),
            OpenApiParameter("segment_id", str, OpenApiParameter.QUERY, required=False),
            OpenApiParameter("limit", int, OpenApiParameter.QUERY, required=False),
            OpenApiParameter("offset", int, OpenApiParameter.QUERY, required=False),
        ],
        responses={200: OpenApiResponse(description="Tous les users ; pending=true = file RH")},
    )
    def get(self, request):
        return Response({"success": True, "data": list_users(request=request)})

    @extend_schema(
        tags=["Admin"],
        request=AdminUserCreateSerializer,
        responses={
            201: OpenApiResponse(description="Compte USER hors AD"),
            400: OpenApiResponse(description="FIELD_FORBIDDEN / WEAK_PASSWORD / REGION_INVALID"),
            409: OpenApiResponse(description="EMAIL_TAKEN / MATRICULE_TAKEN"),
        },
    )
    def post(self, request):
        raw = request.data or {}
        ser = AdminUserCreateSerializer(data=raw)
        ser.is_valid(raise_exception=True)
        payload = {**ser.validated_data}
        if "role_code" in raw:
            payload["role_code"] = raw["role_code"]
        if "role_id" in raw:
            payload["role_id"] = raw["role_id"]
        data = create_local_user(data=payload, actor=request.user, ip=client_ip(request))
        return Response({"success": True, "data": data}, status=201)


class AdminUserDetailView(APIView):
    required_permission = "iam.user.read"

    @extend_schema(
        tags=["Admin"],
        responses={
            200: OpenApiResponse(description="Fiche admin (sans secrets)"),
            404: OpenApiResponse(description="NOT_FOUND"),
        },
    )
    def get(self, request, pk):
        return Response({"success": True, "data": get_user_detail(pk)})


class AdminUserDisableView(APIView):
    required_permission = "iam.user.disable"

    @extend_schema(
        tags=["Admin"],
        request=AdminReasonSerializer,
        responses={
            200: OpenApiResponse(description="Désactivé, sessions tuées"),
            400: OpenApiResponse(description="LDAP_MANAGED / CANNOT_ACT_ON_SELF"),
            409: OpenApiResponse(description="LAST_ADMIN"),
        },
    )
    def post(self, request, pk):
        ser = AdminReasonSerializer(data=request.data or {})
        ser.is_valid(raise_exception=True)
        data = disable_user(
            user_id=pk,
            actor=request.user,
            ip=client_ip(request),
            reason=ser.validated_data.get("reason") or "",
        )
        return Response({"success": True, "data": data})


class AdminUserEnableView(APIView):
    required_permission = "iam.user.enable"

    @extend_schema(
        tags=["Admin"],
        request=AdminReasonSerializer,
        responses={
            200: OpenApiResponse(description="Réactivé (ne déverrouille pas)"),
            400: OpenApiResponse(description="LDAP_MANAGED / STILL_PENDING"),
        },
    )
    def post(self, request, pk):
        ser = AdminReasonSerializer(data=request.data or {})
        ser.is_valid(raise_exception=True)
        data = enable_user(
            user_id=pk,
            actor=request.user,
            ip=client_ip(request),
            reason=ser.validated_data.get("reason") or "",
        )
        return Response({"success": True, "data": data})


class AdminUserPasswordView(APIView):
    required_permission = "iam.user.reset_password"

    @extend_schema(
        tags=["Admin"],
        request=AdminPasswordSerializer,
        responses={
            200: OpenApiResponse(description="ok, sans password"),
            400: OpenApiResponse(description="CANNOT_ACT_ON_SELF / WEAK_PASSWORD / PASSWORD_REUSED"),
        },
    )
    def post(self, request, pk):
        ser = AdminPasswordSerializer(data=request.data or {})
        ser.is_valid(raise_exception=True)
        data = reset_user_password(
            user_id=pk,
            new_password=ser.validated_data["new_password"],
            actor=request.user,
            ip=client_ip(request),
        )
        return Response({"success": True, "data": data})


class AdminUserRevokeAllView(APIView):
    required_permission = "iam.session.revoke_other"

    @extend_schema(
        tags=["Admin"],
        responses={
            200: OpenApiResponse(description="Sessions révoquées"),
            400: OpenApiResponse(description="CANNOT_ACT_ON_SELF"),
        },
    )
    def post(self, request, pk):
        data = revoke_all_sessions(user_id=pk, actor=request.user, ip=client_ip(request))
        return Response({"success": True, "data": data})


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
