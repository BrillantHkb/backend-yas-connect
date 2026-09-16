"""AUTH-E : /me/devices* (JWT + iam.device.*) + admin (iam.device.manage)."""

from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.iam.exceptions import AuthAPIError
from apps.iam.serializers.devices import (
    DeviceCurrentPatchSerializer,
    DeviceListEnvelopeSerializer,
    DeviceOutSerializer,
    DevicePatchSerializer,
)
from apps.iam.services import rate_limit_service
from apps.iam.services.device_service import (
    clear_compromise,
    compromise_admin,
    compromise_owned,
    current_device,
    current_device_id,
    list_my_devices,
    patch_current_device,
    patch_owned_device,
    revoke_device,
    serialize_device,
)
from apps.notifications.services import push_worker


class DeviceListView(APIView):
    """GET /api/v1/me/devices — soi uniquement."""

    required_permission = "iam.device.read"

    @extend_schema(
        tags=["Devices"],
        responses={200: DeviceListEnvelopeSerializer},
        description="Liste des appareils du JWT. `push_token` jamais renvoyé.",
    )
    def get(self, request):
        devices = list_my_devices(
            user=request.user,
            current_device_id=current_device_id(request),
        )
        return Response({"success": True, "data": {"devices": devices}})


class DeviceCurrentPatchView(APIView):
    """PATCH /api/v1/me/devices/current — heartbeat session."""

    required_permission = "iam.device.update"

    @extend_schema(
        tags=["Devices"],
        request=DeviceCurrentPatchSerializer,
        responses={
            200: DeviceOutSerializer,
            403: OpenApiResponse(description="DEVICE_COMPROMISED / DEVICE_JAILBROKEN"),
        },
    )
    def patch(self, request):
        ser = DeviceCurrentPatchSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        device = patch_current_device(device=current_device(request), spec=ser.validated_data)
        return Response(
            {
                "success": True,
                "data": serialize_device(
                    device, current_device_id=current_device_id(request)
                ),
            }
        )


class DevicePushTestView(APIView):
    """POST /api/v1/me/devices/current/push-test — NOTIF-17, diagnostic, 1/30 s."""

    required_permission = "iam.device.update"

    @extend_schema(
        tags=["Devices"],
        parameters=[
            OpenApiParameter(
                "channel", str, OpenApiParameter.QUERY, required=False,
                enum=["alert", "voip", "both"],
            ),
        ],
        responses={200: OpenApiResponse(description="Diagnostic canaux"), 429: OpenApiResponse()},
    )
    def post(self, request):
        device = current_device(request)
        if rate_limit_service.is_push_test_limited(device.id):
            raise AuthAPIError(429, "RATE_LIMITED", "Trop de tests, réessayez dans 30 secondes.")
        rate_limit_service.push_test_hit(device.id)
        channel = (request.query_params.get("channel") or "both").strip().lower()
        channels = push_worker.send_test(device, channel)
        return Response(
            {
                "success": True,
                "data": {"emitted_at": timezone.now().isoformat(), "channels": channels},
            }
        )


class DevicePatchView(APIView):
    """PATCH /api/v1/me/devices/{id} — rename / trusted."""

    required_permission = "iam.device.update"

    @extend_schema(
        tags=["Devices"],
        request=DevicePatchSerializer,
        responses={
            200: DeviceOutSerializer,
            400: OpenApiResponse(description="DEVICE_COMPROMISED si trusted sur banni"),
            404: OpenApiResponse(description="NOT_FOUND"),
        },
    )
    def patch(self, request, pk):
        ser = DevicePatchSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        device = patch_owned_device(
            user=request.user,
            device_id=pk,
            device_name=data.get("device_name"),
            trusted=data.get("trusted"),
        )
        return Response(
            {
                "success": True,
                "data": serialize_device(
                    device, current_device_id=current_device_id(request)
                ),
            }
        )


class DeviceRevokeView(APIView):
    """POST /api/v1/me/devices/{id}/revoke — kill + untrust. Relogin OK."""

    required_permission = "iam.device.revoke"

    @extend_schema(
        tags=["Devices"],
        responses={
            200: OpenApiResponse(description="Sessions tuées ; ligne conservée"),
            404: OpenApiResponse(description="NOT_FOUND"),
        },
    )
    def post(self, request, pk):
        revoke_device(user=request.user, device_id=pk)
        return Response({"success": True, "data": {"revoked": True}})


class DeviceCompromiseView(APIView):
    """POST /api/v1/me/devices/{id}/compromise — pas l’appareil courant."""

    required_permission = "iam.device.compromise"

    @extend_schema(
        tags=["Devices"],
        responses={
            200: OpenApiResponse(description="compromised ; prochain login 403"),
            400: OpenApiResponse(description="CANNOT_COMPROMISE_CURRENT"),
            404: OpenApiResponse(description="NOT_FOUND"),
        },
    )
    def post(self, request, pk):
        compromise_owned(
            user=request.user,
            device_id=pk,
            current_device_id=current_device_id(request),
        )
        return Response({"success": True, "data": {"compromised": True}})


class AdminDeviceCompromiseView(APIView):
    """POST /api/v1/admin/devices/{id}/compromise — y compris courant cible."""

    required_permission = "iam.device.manage"

    @extend_schema(
        tags=["Admin"],
        responses={
            200: OpenApiResponse(description="Kill + compromised"),
            404: OpenApiResponse(description="NOT_FOUND"),
        },
    )
    def post(self, request, pk):
        compromise_admin(device_id=pk)
        return Response({"success": True, "data": {"compromised": True}})


class AdminDeviceClearCompromiseView(APIView):
    """POST /api/v1/admin/devices/{id}/clear-compromise — pas de trusted auto."""

    required_permission = "iam.device.manage"

    @extend_schema(
        tags=["Admin"],
        responses={
            200: OpenApiResponse(description="compromised=false"),
            404: OpenApiResponse(description="NOT_FOUND"),
        },
    )
    def post(self, request, pk):
        clear_compromise(device_id=pk)
        return Response({"success": True, "data": {"cleared": True}})
