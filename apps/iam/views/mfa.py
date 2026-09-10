"""Vues AUTH-C : verify public ; regen JWT (session déjà MFA)."""

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.iam.serializers.auth import (
    AuthSuccessSerializer,
    BackupRegenSerializer,
    MfaVerifySerializer,
)
from apps.iam.services.auth_service import client_ip
from apps.iam.services.mfa_service import regenerate_backup_codes, verify_mfa


class MfaVerifyView(APIView):
    """POST /api/v1/auth/mfa/verify — public. Seul chemin vers le JWT."""

    authentication_classes = []  # pas de Bearer : le JWT n’existe pas encore
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Auth"],
        auth=[],
        request=MfaVerifySerializer,
        responses={
            200: AuthSuccessSerializer,
            400: OpenApiResponse(description="otp XOR backup ; pas de backup en enroll"),
            401: OpenApiResponse(description="INVALID_CREDENTIALS / MFA_CHALLENGE_EXPIRED"),
        },
        description=(
            "2e facteur : `otp` Authenticator ou `backup_code`. "
            "Enroll : uniquement `otp` ; `backup_codes` renvoyés une fois."
        ),
    )
    def post(self, request):
        ser = MfaVerifySerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = verify_mfa(
            mfa_token=ser.validated_data["mfa_token"],
            otp=ser.validated_data.get("otp"),
            backup_code=ser.validated_data.get("backup_code"),
            ip=client_ip(request),
        )
        return Response({"success": True, "data": data})  # JWT + backup_codes si enroll


class BackupRegenView(APIView):
    """POST /api/v1/auth/mfa/backup-codes/regenerate — JWT déjà MFA."""

    required_permission = "iam.mfa.regenerate"

    @extend_schema(
        tags=["Auth"],
        request=BackupRegenSerializer,
        responses={
            200: OpenApiResponse(description="Nouveaux backup_codes une fois"),
            401: OpenApiResponse(description="TOTP faux"),
            403: OpenApiResponse(description="MFA_NOT_ENROLLED"),
        },
    )
    def post(self, request):
        ser = BackupRegenSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        codes = regenerate_backup_codes(user=request.user, otp=ser.validated_data["otp"])
        return Response({"success": True, "data": {"backup_codes": codes}})
