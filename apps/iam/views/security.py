"""AUTH-I : historique de connexions, change email, verify public. Pas HasPermission."""

from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.iam.serializers.register import VerifyEmailSerializer
from apps.iam.serializers.security import (
    EmailChangeEnvelopeSerializer,
    EmailChangeSerializer,
    LoginHistoryEnvelopeSerializer,
)
from apps.iam.services.auth_service import client_ip
from apps.iam.services.email_verification_service import (
    request_email_change,
    resend_email_change,
    verify_email,
)
from apps.iam.services.security_service import list_logins, parse_login_query


class LoginHistoryView(APIView):
    """GET /api/v1/me/security/logins — owner, portes AUTH-F."""

    required_permission = "iam.login.read"

    @extend_schema(
        tags=["Me"],
        parameters=[
            OpenApiParameter(
                name="limit",
                type=int,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Défaut 50, max 100",
            ),
            OpenApiParameter(
                name="before",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Cursor created_at ISO",
            ),
        ],
        responses={
            200: LoginHistoryEnvelopeSerializer,
            403: OpenApiResponse(description="TOS_REQUIRED / ONBOARDING_REQUIRED"),
        },
        description="Succès et échecs du porteur. Geo NULL OK. Jamais de hash.",
    )
    def get(self, request):
        limit, before = parse_login_query(request)
        logins = list_logins(user=request.user, limit=limit, before=before)
        return Response({"success": True, "data": {"logins": logins}})


class EmailChangeView(APIView):
    """POST /api/v1/me/email — JWT. users.email inchangé jusqu’au verify."""

    required_permission = "iam.email.change"

    @extend_schema(
        tags=["Me"],
        request=EmailChangeSerializer,
        responses={
            202: EmailChangeEnvelopeSerializer,
            400: OpenApiResponse(description="EMAIL_CHANGE_FORBIDDEN / EMAIL_UNCHANGED"),
            409: OpenApiResponse(description="CONFLICT"),
        },
        description="ldap_dn interdit. 202 : ticket EMAIL_CHANGE, adresse pas encore posée.",
    )
    def post(self, request):
        ser = EmailChangeSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        request_email_change(
            user=request.user,
            email=ser.validated_data["email"],
            ip=client_ip(request),
        )
        return Response({"success": True}, status=202)


class EmailResendView(APIView):
    """POST /api/v1/me/email/resend — JWT. 429 si trop de renvois."""

    required_permission = "iam.email.change"

    @extend_schema(
        tags=["Me"],
        request=None,
        responses={
            200: EmailChangeEnvelopeSerializer,
            400: OpenApiResponse(description="INVALID_TOKEN"),
            429: OpenApiResponse(description="EMAIL_RESEND_RATE_LIMITED"),
        },
    )
    def post(self, request):
        resend_email_change(user=request.user, ip=client_ip(request))
        return Response({"success": True})


class EmailVerifyView(APIView):
    """POST /api/v1/auth/email/verify — public (alias register/verify-email)."""

    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Auth"],
        auth=[],
        request=VerifyEmailSerializer,
        responses={
            200: OpenApiResponse(description="verified_at ; EMAIL_CHANGE pose users.email"),
            400: OpenApiResponse(description="INVALID_TOKEN"),
        },
    )
    def post(self, request):
        ser = VerifyEmailSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        verify_email(token=ser.validated_data["token"])
        return Response({"success": True, "data": {"verified": True}})
