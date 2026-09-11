"""Serializers PROF-B : GET/PATCH /me/preferences + fragment editable."""

from rest_framework import serializers


class EditableSerializer(serializers.Serializer):
    first_name = serializers.BooleanField()
    last_name = serializers.BooleanField()
    username = serializers.BooleanField()
    phone = serializers.BooleanField()
    matricule = serializers.BooleanField()
    job_title = serializers.BooleanField()


class PreferencesBodySerializer(serializers.Serializer):
    """PATCH /me/preferences : partiel, au moins un champ. Extras = UNKNOWN_FIELD métier."""

    language = serializers.CharField(max_length=8, required=False)
    timezone = serializers.CharField(max_length=64, required=False)
    notification_sound = serializers.BooleanField(required=False)
    auto_download_media = serializers.BooleanField(required=False)
    read_receipts = serializers.BooleanField(required=False)
    typing_indicator = serializers.BooleanField(required=False)


class PreferencesPublicSerializer(serializers.Serializer):
    language = serializers.CharField()
    timezone = serializers.CharField()
    notification_sound = serializers.BooleanField()
    auto_download_media = serializers.BooleanField()
    read_receipts = serializers.BooleanField()
    typing_indicator = serializers.BooleanField()
    last_updated = serializers.CharField(allow_null=True)


class PreferencesEnvelopeSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    data = PreferencesPublicSerializer()
