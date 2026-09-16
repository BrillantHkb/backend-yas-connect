"""MESSAGERIE-E : shapes DRF (signets)."""

from rest_framework import serializers


class BookmarkSerializer(serializers.Serializer):
    note = serializers.CharField(required=False, allow_blank=True, default="")
