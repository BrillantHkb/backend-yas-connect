"""AUTH-E : /me/devices* (JWT) + admin compromise (JWT + ADMIN)."""

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.iam.exceptions import AuthAPIError
from apps.iam.middlewares.permissions import IsAdminRole
from apps.iam.serializers.devices import (
    DeviceCurrentPatchSerializer,
    DeviceListEnvelopeSerializer,
    DeviceOutSerializer,
    DevicePatchSerializer,
)
from apps.iam.services.device_service import (
    MSG_NOT_FOUND,
    clear_compromise,
    compromise_admin,
    compromise_owned,
    list_my_devices,
    patch_current_device,
    patch_owned_device,
    revoke_device,
    serialize_device,
)


def _current_device_id(request):
    session = getattr(request, "yas_session", None)
    if session is None:
        return None
    return session.device_id


def _current_device(request):
    session = getattr(request, "yas_session", None)
    if session is None or session.device_id is None:
        raise AuthAPIError(404, "NOT_FOUND", MSG_NOT_FOUND)
    device = session.device
    if device is None:
        raise AuthAPIError(404, "NOT_FOUND", MSG_NOT_FOUND)
    return device


class DeviceListView(APIView):
    """GET /api/v1/me/devices — soi uniquement."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Devices"],
        responses={200: DeviceListEnvelopeSerializer},
        description="Liste des appareils du JWT. `push_token` jamais renvoyé.",
    )
    def get(self, request):
        devices = list_my_devices(
            user=request.user,
            current_device_id=_current_device_id(request),
        )
        return Response({"success": True, "data": {"devices": devices}})


class DeviceCurrentPatchView(APIView):
    """PATCH /api/v1/me/devices/current — heartbeat session."""

    permission_classes = [IsAuthenticated]

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
        device = patch_current_device(device=_current_device(request), spec=ser.validated_data)
        return Response(
            {
                "success": True,
                "data": serialize_device(
                    device, current_device_id=_current_device_id(request)
                ),
            }
        )


class DevicePatchView(APIView):
    """PATCH /api/v1/me/devices/{id} — rename / trusted."""

    permission_classes = [IsAuthenticated]

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
                    device, current_device_id=_current_device_id(request)
                ),
            }
        )


class DeviceRevokeView(APIView):
    """POST /api/v1/me/devices/{id}/revoke — kill + untrust. Relogin OK."""

    permission_classes = [IsAuthenticated]

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

    permission_classes = [IsAuthenticated]

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
            current_device_id=_current_device_id(request),
        )
        return Response({"success": True, "data": {"compromised": True}})


class AdminDeviceCompromiseView(APIView):
    """POST /api/v1/admin/devices/{id}/compromise — y compris courant cible."""

    permission_classes = [IsAuthenticated, IsAdminRole]

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

    permission_classes = [IsAuthenticated, IsAdminRole]

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
