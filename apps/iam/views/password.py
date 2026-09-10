"""AUTH-G : changement JWT + forgot / verify / reset publics. Pas HasPermission."""

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.iam.serializers.password import (
    PasswordChangeSerializer,
    PasswordForgotEnvelopeSerializer,
    PasswordForgotSerializer,
    PasswordOkEnvelopeSerializer,
    PasswordResetSerializer,
    PasswordResetTicketEnvelopeSerializer,
    PasswordResetVerifySerializer,
)
from apps.iam.services.auth_service import client_ip
from apps.iam.services.password_service import (
    MSG_FORGOT,
    request_reset,
    reset_password,
    rotate_password,
    verify_reset_mfa,
)


class PasswordChangeView(APIView):
    """POST /api/v1/me/password — JWT, portes AUTH-F."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Me"],
        request=PasswordChangeSerializer,
        responses={
            200: PasswordOkEnvelopeSerializer,
            400: OpenApiResponse(
                description="INVALID_OLD_PASSWORD / WEAK_PASSWORD / PASSWORD_REUSED / SAME_PASSWORD"
            ),
            403: OpenApiResponse(description="TOS_REQUIRED / ONBOARDING_REQUIRED"),
        },
        description="Change le MDP applicatif (pas AD). logout_others défaut true (autres sessions tuées).",
    )
    def post(self, request):
        ser = PasswordChangeSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        rotate_password(
            user=request.user,
            old_password=ser.validated_data["old_password"],
            new_password=ser.validated_data["new_password"],
            logout_others=ser.validated_data.get("logout_others", True),
            current_session=getattr(request, "yas_session", None),
            ip=client_ip(request),
        )
        return Response({"success": True})


class PasswordForgotView(APIView):
    """POST /api/v1/auth/password/forgot — toujours 200, zéro envoi."""

    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Auth"],
        auth=[],
        request=PasswordForgotSerializer,
        responses={200: PasswordForgotEnvelopeSerializer},
        description="Anti-énumération : même 200. Preuve = Authenticator, pas de mail.",
    )
    def post(self, request):
        ser = PasswordForgotSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        request_reset(
            email=ser.validated_data.get("email"),
            username=ser.validated_data.get("username"),
            ip=client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
        )
        return Response({"success": True, "message": MSG_FORGOT})


class PasswordResetVerifyView(APIView):
    """POST /api/v1/auth/password/reset/verify — TOTP / backup → ticket."""

    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Auth"],
        auth=[],
        request=PasswordResetVerifySerializer,
        responses={
            200: PasswordResetTicketEnvelopeSerializer,
            400: OpenApiResponse(description="MFA_INVALID ou VALIDATION_ERROR"),
        },
        description="Ne consomme pas le ticket (used_at NULL). channel interdit.",
    )
    def post(self, request):
        ser = PasswordResetVerifySerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = verify_reset_mfa(
            email=ser.validated_data.get("email"),
            username=ser.validated_data.get("username"),
            otp=ser.validated_data.get("otp"),
            backup_code=ser.validated_data.get("backup_code"),
            ip=client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
        )
        return Response({"success": True, "data": data})


class PasswordResetView(APIView):
    """POST /api/v1/auth/password/reset — ticket + nouveau MDP. Pas de JWT."""

    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Auth"],
        auth=[],
        request=PasswordResetSerializer,
        responses={
            200: PasswordOkEnvelopeSerializer,
            400: OpenApiResponse(description="INVALID_TOKEN / WEAK_PASSWORD / PASSWORD_REUSED"),
        },
        description="logout_all défaut true. Ne déverrouille pas un compte locked.",
    )
    def post(self, request):
        ser = PasswordResetSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        reset_password(
            reset_token=ser.validated_data["reset_token"],
            new_password=ser.validated_data["new_password"],
            logout_all=ser.validated_data.get("logout_all", True),
            ip=client_ip(request),
        )
        return Response({"success": True})
