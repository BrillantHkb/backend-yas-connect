"""Vues publiques AUTH-D (inscription)."""

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.iam.serializers import MfaChallengeEnvelopeSerializer
from apps.iam.serializers_register import (
    CheckAdSerializer,
    RegisterAdSerializer,
    RegisterLocalSerializer,
    ResendVerificationSerializer,
    VerifyEmailSerializer,
)
from apps.iam.services.auth_service import client_ip
from apps.iam.services.register_service import (
    MSG_PENDING_CREATED,
    check_ad,
    register_ad,
    register_local,
    resend_verification,
    verify_email,
)


def _profile(data: dict) -> dict:
    """Champs RH communs D02/D03. Pas d’UPN/sAM : l’AD les impose en register/ad."""
    return {
        "first_name": data["first_name"],
        "last_name": data["last_name"],
        "phone": data["phone"],
        "job_title": data["job_title"],
        "language": data.get("language") or "fr",
        "region_id": data["region_id"],
        "segment_id": data["segment_id"],
        "matricule": data.get("matricule") or None,
        "avatar_id": data.get("avatar_id"),
    }


class CheckAdView(APIView):
    authentication_classes = []  # public : pas de Bearer
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Auth"],
        auth=[],
        request=CheckAdSerializer,
        responses={
            200: OpenApiResponse(description="ad_available true|false (jamais 401)"),
            400: OpenApiResponse(description="VALIDATION_ERROR"),
            503: OpenApiResponse(description="DIRECTORY_UNAVAILABLE"),
        },
        description="Pré-check AD. Réponse toujours 200 sauf annuaire down.",
    )
    def post(self, request):
        ser = CheckAdSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = check_ad(
            email=ser.validated_data.get("email"),
            username=ser.validated_data.get("username"),
            password=ser.validated_data["password"],
            ip=client_ip(request),
        )
        return Response({"success": True, "data": data})  # 200 même si ad_available=false


class RegisterAdView(APIView):
    authentication_classes = []  # public : JIT unique (création user AD)
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Auth"],
        auth=[],
        request=RegisterAdSerializer,
        responses={
            200: MfaChallengeEnvelopeSerializer,
            400: OpenApiResponse(description="WEAK_PASSWORD / REGION_INVALID / SEGMENT_INVALID"),
            401: OpenApiResponse(description="INVALID_CREDENTIALS"),
            409: OpenApiResponse(description="CONFLICT UPN / sAMAccountName"),
            503: OpenApiResponse(description="DIRECTORY_UNAVAILABLE"),
        },
        description="Inscription AD. Seul JIT. 200 = mfa_required (QR enroll).",
    )
    def post(self, request):
        ser = RegisterAdSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        payload = register_ad(
            email=data.get("email"),
            username=data.get("username"),
            password_ad=data["password_ad"],
            password=data["password"],
            profile=_profile(data),
            device_spec=data["device"],
            ip=client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
        )
        return Response({"success": True, "data": payload})  # begin_mfa, pas de JWT


class RegisterLocalView(APIView):
    authentication_classes = []  # public : 201 sans JWT
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Auth"],
        auth=[],
        request=RegisterLocalSerializer,
        responses={
            201: OpenApiResponse(description="Compte créé, pending RH"),
            400: OpenApiResponse(description="WEAK_PASSWORD / REGION / SEGMENT"),
            409: OpenApiResponse(description="CONFLICT ou AD_ACCOUNT_EXISTS"),
        },
        description="Inscription hors AD. Pas de JWT. Validation RH requise.",
    )
    def post(self, request):
        ser = RegisterLocalSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        payload = register_local(
            email=data["email"],
            password=data["password"],
            profile=_profile(data),
            ip=client_ip(request),
        )
        return Response(
            {"success": True, "message": MSG_PENDING_CREATED, "data": payload},
            status=201,
        )


class VerifyEmailView(APIView):
    authentication_classes = []  # token dans le body, pas de Bearer
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Auth"],
        auth=[],
        request=VerifyEmailSerializer,
        responses={
            200: OpenApiResponse(description="verified_at posé ; is_active inchangé"),
            400: OpenApiResponse(description="INVALID_TOKEN"),
        },
    )
    def post(self, request):
        ser = VerifyEmailSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        verify_email(token=ser.validated_data["token"])
        return Response({"success": True, "data": {"verified": True}})  # is_active inchangé


class ResendVerificationView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]  # 200 même si e-mail inconnu

    @extend_schema(
        tags=["Auth"],
        auth=[],
        request=ResendVerificationSerializer,
        responses={200: OpenApiResponse(description="Toujours 200 (anti-énumération)")},
    )
    def post(self, request):
        ser = ResendVerificationSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        resend_verification(email=ser.validated_data["email"], ip=client_ip(request))
        return Response({"success": True, "data": {"sent": True}})  # 200 même si inconnu
