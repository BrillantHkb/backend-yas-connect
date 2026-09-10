"""Serializers AUTH-H : liste de sessions + heartbeat. Jamais hash / JTI."""

from rest_framework import serializers


class SessionOutSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    device_id = serializers.UUIDField(allow_null=True)
    device_name = serializers.CharField()
    platform = serializers.CharField(allow_null=True)
    ip_address = serializers.CharField(allow_null=True)
    login_at = serializers.CharField(allow_null=True)
    last_activity = serializers.CharField()
    login_method = serializers.CharField()
    is_current = serializers.BooleanField()


class SessionListDataSerializer(serializers.Serializer):
    sessions = SessionOutSerializer(many=True)


class SessionListEnvelopeSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    data = SessionListDataSerializer()


class HeartbeatDataSerializer(serializers.Serializer):
    last_activity = serializers.CharField()


class HeartbeatEnvelopeSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    data = HeartbeatDataSerializer()


class SessionOkEnvelopeSerializer(serializers.Serializer):
    success = serializers.BooleanField()
