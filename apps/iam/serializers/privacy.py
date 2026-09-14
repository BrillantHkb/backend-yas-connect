"""Serializers PROF-C : GET/PATCH /me/privacy."""

from rest_framework import serializers


class PrivacyBodySerializer(serializers.Serializer):
    """PATCH /me/privacy : partiel, au moins un champ. Extras = UNKNOWN_FIELD métier."""

    last_seen_visibility = serializers.CharField(required=False)
    profile_photo_visibility = serializers.CharField(required=False)
    online_status_visibility = serializers.CharField(required=False)
    read_receipts_enabled = serializers.BooleanField(required=False)
    typing_indicator_enabled = serializers.BooleanField(required=False)
    allow_calls = serializers.BooleanField(required=False)
    allow_mentions = serializers.BooleanField(required=False)
    allow_group_invites = serializers.BooleanField(required=False)


class PrivacyPublicSerializer(serializers.Serializer):
    last_seen_visibility = serializers.CharField()
    profile_photo_visibility = serializers.CharField()
    online_status_visibility = serializers.CharField()
    read_receipts_enabled = serializers.BooleanField()
    typing_indicator_enabled = serializers.BooleanField()
    allow_calls = serializers.BooleanField()
    allow_mentions = serializers.BooleanField()
    allow_group_invites = serializers.BooleanField()
    updated_at = serializers.CharField(allow_null=True)


class PrivacyEnvelopeSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    data = PrivacyPublicSerializer()
