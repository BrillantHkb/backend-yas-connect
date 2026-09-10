"""AUTH-J : start / poll publics ; confirm JWT (téléphone déjà MFA)."""

from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.iam.serializers.devices import DeviceLinkConfirmSerializer, DeviceLinkStartSerializer
from apps.iam.services.auth_service import client_ip
from apps.iam.services.device_link_service import (
    confirm_device_link,
    poll_device_link,
    start_device_link,
)


class DeviceLinkStartView(APIView):
    """POST /api/v1/auth/device-link/start — public. Pas de JWT tant que TOTP OK."""

    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Auth"],
        auth=[],
        request=DeviceLinkStartSerializer,
        responses={
            200: OpenApiResponse(description="challenge_id + waiter_secret + qr_payload"),
            400: OpenApiResponse(description="VALIDATION_ERROR"),
            429: OpenApiResponse(description="RATE_LIMITED (10 / min / IP)"),
        },
        description=(
            "Nouvel écran : crée un challenge 120 s. "
            "`waiter_secret` reste en mémoire du waiter, **jamais** dans le QR. "
            "QR : `yasconnect://device-link/v1?cid=…` (pas otpauth://)."
        ),
    )
    def post(self, request):
        ser = DeviceLinkStartSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = start_device_link(
            device_spec=ser.validated_data["device"],
            ip=client_ip(request),
        )
        return Response({"success": True, "data": data})


class DeviceLinkStatusView(APIView):
    """GET /api/v1/auth/device-link/{id} — poll waiter. Header secret obligatoire."""

    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Auth"],
        auth=[],
        parameters=[
            OpenApiParameter(
                name="X-Device-Link-Secret",
                type=str,
                location=OpenApiParameter.HEADER,
                required=True,
                description="waiter_secret renvoyé au start. Jamais dans le QR.",
            )
        ],
        responses={
            200: OpenApiResponse(description="PENDING ou APPROVED + tokens (1re lecture)"),
            403: OpenApiResponse(description="DEVICE_LINK_FORBIDDEN"),
            410: OpenApiResponse(description="DEVICE_LINK_EXPIRED"),
        },
        description="Poll ~2 s. APPROVED = tokens complete_login, cache alors supprimé.",
    )
    def get(self, request, challenge_id):
        data = poll_device_link(
            challenge_id=challenge_id,
            waiter_secret=request.META.get("HTTP_X_DEVICE_LINK_SECRET"),
        )
        return Response({"success": True, "data": data})


class DeviceLinkConfirmView(APIView):
    """POST /api/v1/me/devices/link — téléphone JWT. TOTP obligatoire, pas de backup."""

    required_permission = "iam.device.update"

    @extend_schema(
        tags=["Devices"],
        request=DeviceLinkConfirmSerializer,
        responses={
            200: OpenApiResponse(description="linked + device_id, sans JWT"),
            400: OpenApiResponse(description="otp manquant / backup / DEVICE_LINK_SELF"),
            401: OpenApiResponse(description="INVALID_CREDENTIALS (TOTP faux)"),
            403: OpenApiResponse(
                description="DEVICE_COMPROMISED / DEVICE_JAILBROKEN / MFA_NOT_ENROLLED"
            ),
            409: OpenApiResponse(description="DEVICE_UUID_TAKEN"),
            410: OpenApiResponse(description="DEVICE_LINK_EXPIRED"),
        },
        description=(
            "Après scan caméra Connect : code Authenticator. "
            "Pas de backup. Tokens remis au waiter (poll), pas au téléphone."
        ),
    )
    def post(self, request):
        ser = DeviceLinkConfirmSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        session = getattr(request, "yas_session", None)
        phone_device = session.device if session is not None else None
        data = confirm_device_link(
            user=request.user,
            challenge_id=ser.validated_data["challenge_id"],
            otp=ser.validated_data.get("otp"),
            backup_code=ser.validated_data.get("backup_code") or None,
            phone_device=phone_device,
            ip=client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
        )
        return Response({"success": True, "data": data})
