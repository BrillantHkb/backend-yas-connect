"""MEDIA-B : shape DRF (PATCH image)."""

from rest_framework import serializers


class ImageUpdateSerializer(serializers.Serializer):
    annotated = serializers.BooleanField(required=False)
    blurred = serializers.BooleanField(required=False)
    derivative_upload_id = serializers.UUIDField(required=False, allow_null=True)
