"""PATCH /me/presence + POST /me/presence/heartbeat — PRES-A. Après CGU + wizard."""

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.iam.serializers.presence import (
    PresenceBodySerializer,
    PresenceEnvelopeSerializer,
    PresenceHeartbeatEnvelopeSerializer,
)
from apps.iam.services.auth_service import client_ip
from apps.iam.services.presence_service import heartbeat, patch_presence


class MePresenceView(APIView):
    required_permission = "iam.presence.update"

    @extend_schema(
        tags=["Me"],
        request=PresenceBodySerializer,
        responses={
            200: PresenceEnvelopeSerializer,
            400: OpenApiResponse(
                description="STATUS_NOT_SETTABLE / STATUS_RESERVED / STATUS_UNKNOWN / "
                "FIELD_UNKNOWN / UNKNOWN_FIELD / VALIDATION_ERROR"
            ),
        },
        description="Message 0–140 ; seul status=ONLINE est posable (clear sticky réunion).",
    )
    def patch(self, request):
        data = patch_presence(
            user=request.user,
            data=request.data or {},
            actor=request.user,
            ip=client_ip(request),
        )
        return Response({"success": True, "data": data})


class MePresenceHeartbeatView(APIView):
    required_permission = "iam.presence.heartbeat"

    @extend_schema(
        tags=["Me"],
        request=None,
        responses={200: PresenceHeartbeatEnvelopeSerializer},
        description="Secours sans WS : rafraîchit la liveness Redis (TTL 90 s).",
    )
    def post(self, request):
        session = getattr(request, "yas_session", None)
        device_id = session.device_id if session is not None else None
        data = heartbeat(user=request.user, session=session, device_id=device_id)
        return Response({"success": True, "data": data})
