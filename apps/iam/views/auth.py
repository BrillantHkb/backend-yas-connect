"""Contrats HTTP AUTH-A. Pas de JWT ici : AllowAny + authentication_classes vides."""

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.iam.serializers.auth import (
    AuthSuccessSerializer,
    LoginSerializer,
    MfaChallengeEnvelopeSerializer,
    RefreshSerializer,
)
from apps.iam.services.auth_service import client_ip, login, login_ldap, refresh


class LoginView(APIView):
    """POST /api/v1/auth/login — public (AUTH-01 … 12)."""

    authentication_classes = []  # pas de Bearer : on n’a pas encore de token
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Auth"],
        auth=[],  # endpoint public : pas de cadenas Bearer
        request=LoginSerializer,
        responses={
            200: MfaChallengeEnvelopeSerializer,
            400: OpenApiResponse(description="VALIDATION_ERROR (email XOR username, device)"),
            401: OpenApiResponse(description="INVALID_CREDENTIALS (inconnu / MDP / rate-limit)"),
            403: OpenApiResponse(description="ACCOUNT_PENDING / DISABLED / LOCKED"),
        },
        description=(
            "Connexion locale. Facteur 1 : identifiant + password + device. "
            "200 = mfa_required (pas de JWT). TOTP : POST /mfa/verify."
        ),
    )
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)  # 400 VALIDATION_ERROR si device / xor email
        data = login(
            email=serializer.validated_data.get("email"),
            username=serializer.validated_data.get("username"),
            password=serializer.validated_data["password"],
            ip=client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
            device_spec=serializer.validated_data["device"],
        )
        return Response({"success": True, "data": data})


class RefreshView(APIView):
    """POST /api/v1/auth/refresh — public (AUTH-10). Rotation du refresh opaque."""

    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Auth"],
        auth=[],
        request=RefreshSerializer,
        responses={
            200: AuthSuccessSerializer,
            400: OpenApiResponse(description="VALIDATION_ERROR"),
            401: OpenApiResponse(description="INVALID_REFRESH ou FORCE_LOGOUT (réutilisation)"),
        },
        description="Rotation : nouvel access + nouvel refresh. L’ancien hash passe en ROTATED.",
    )
    def post(self, request):
        serializer = RefreshSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = refresh(raw=serializer.validated_data["refresh_token"], ip=client_ip(request))
        return Response({"success": True, "data": data})


class LdapLoginView(APIView):
    """POST /api/v1/auth/login/ldap — public (AUTH-13). User déjà créé par register/ad."""

    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Auth"],
        auth=[],
        request=LoginSerializer,
        responses={
            200: MfaChallengeEnvelopeSerializer,
            400: OpenApiResponse(description="VALIDATION_ERROR"),
            401: OpenApiResponse(description="INVALID_CREDENTIALS (inconnu / bind / UAC)"),
            403: OpenApiResponse(description="ACCOUNT_PENDING / DISABLED / LOCKED après bind OK"),
            503: OpenApiResponse(description="DIRECTORY_UNAVAILABLE"),
        },
        description=(
            "Connexion mot de passe Active Directory. Même body qu’AUTH-A. "
            "200 = mfa_required. Pas de JIT (création = POST /register/ad)."
        ),
    )
    def post(self, request):
        serializer = LoginSerializer(data=request.data)  # même contrat qu’AUTH-A
        serializer.is_valid(raise_exception=True)
        data = login_ldap(
            email=serializer.validated_data.get("email"),
            username=serializer.validated_data.get("username"),
            password=serializer.validated_data["password"],
            ip=client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
            device_spec=serializer.validated_data["device"],
        )
        return Response({"success": True, "data": data})
