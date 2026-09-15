"""NOTIF-A : shape DRF inbox/prefs. Règles = services/notification_service.py."""

from rest_framework import serializers


class NotificationPreferencesPatchSerializer(serializers.Serializer):
    push_enabled = serializers.BooleanField(required=False)
    in_app_enabled = serializers.BooleanField(required=False)
    call_ring_enabled = serializers.BooleanField(required=False)
    message_preview_enabled = serializers.BooleanField(required=False)
    quiet_hours_enabled = serializers.BooleanField(required=False)
    quiet_hours_start = serializers.TimeField(required=False, allow_null=True)
    quiet_hours_end = serializers.TimeField(required=False, allow_null=True)
