"""MEDIA-A : shape DRF upload. Règles = services/upload_service.py."""

from rest_framework import serializers


class UploadInitSerializer(serializers.Serializer):
    filename = serializers.CharField()
    mime_type = serializers.CharField()
    size_bytes = serializers.IntegerField()
    media_type = serializers.CharField()


class UploadCompleteSerializer(serializers.Serializer):
    checksum = serializers.CharField()
