"""MEDIA-D : shape DRF (transcription)."""

from rest_framework import serializers


class TranscribeSerializer(serializers.Serializer):
    language = serializers.CharField(required=False, allow_blank=True, default="")
