"""NOTIF-A : GET/PATCH /notification-preferences (NOTIF-05/06)."""

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.notifications.serializers.notifications import NotificationPreferencesPatchSerializer
from apps.notifications.services.notification_service import (
    get_preferences,
    patch_preferences,
    serialize_preferences,
)


class NotificationPreferencesView(APIView):
    required_permission = "notifications.preferences.manage"

    @extend_schema(tags=["Notifications"], responses={200: OpenApiResponse()})
    def get(self, request):
        prefs = get_preferences(user=request.user)
        return Response({"success": True, "data": serialize_preferences(prefs)})

    @extend_schema(
        tags=["Notifications"],
        request=NotificationPreferencesPatchSerializer,
        responses={200: OpenApiResponse(), 400: OpenApiResponse()},
    )
    def patch(self, request):
        ser = NotificationPreferencesPatchSerializer(data=request.data or {})
        ser.is_valid(raise_exception=True)
        prefs = patch_preferences(user=request.user, data=ser.validated_data)
        return Response({"success": True, "data": serialize_preferences(prefs)})
