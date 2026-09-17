"""MEDIA-A/B/C/D : shape DRF upload. Règles = services/upload_service.py."""

from rest_framework import serializers


class UploadInitSerializer(serializers.Serializer):
    filename = serializers.CharField()
    mime_type = serializers.CharField()
    size_bytes = serializers.IntegerField()
    media_type = serializers.CharField()


class UploadMetadataSerializer(serializers.Serializer):
    """Déclaratif client (§0 jour 28) — jamais vérifié contre le fichier réel."""

    width = serializers.IntegerField(required=False, allow_null=True)
    height = serializers.IntegerField(required=False, allow_null=True)
    duration_seconds = serializers.IntegerField(required=False, allow_null=True)
    codec = serializers.CharField(required=False, allow_blank=True)
    latitude = serializers.DecimalField(
        max_digits=10, decimal_places=7, required=False, allow_null=True
    )
    longitude = serializers.DecimalField(
        max_digits=10, decimal_places=7, required=False, allow_null=True
    )
    captured_at = serializers.DateTimeField(required=False, allow_null=True)
    device_model = serializers.CharField(required=False, allow_blank=True)


class UploadCompleteSerializer(serializers.Serializer):
    checksum = serializers.CharField()
    metadata = UploadMetadataSerializer(required=False)
