"""Serializers PRES-A : PATCH /me/presence + envelopes OpenAPI."""

from rest_framework import serializers


class PresenceBodySerializer(serializers.Serializer):
    """PATCH /me/presence : partiel, au moins status ou status_message."""

    status = serializers.CharField(required=False)
    status_message = serializers.CharField(required=False, allow_blank=True)


class PresencePublicSerializer(serializers.Serializer):
    status = serializers.CharField()
    connection = serializers.CharField()
    availability = serializers.CharField()
    badge = serializers.CharField(allow_null=True)
    status_message = serializers.CharField()
    last_seen = serializers.CharField(allow_null=True)
    last_login = serializers.CharField(allow_null=True)


class PresenceEnvelopeSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    data = PresencePublicSerializer()


class PresenceHeartbeatSerializer(serializers.Serializer):
    at = serializers.CharField()


class PresenceHeartbeatEnvelopeSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    data = PresenceHeartbeatSerializer()
