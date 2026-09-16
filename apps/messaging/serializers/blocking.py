"""MESSAGERIE-F : shapes DRF (blocage)."""

from rest_framework import serializers


class BlockUserSerializer(serializers.Serializer):
    user_id = serializers.UUIDField()
    reason = serializers.CharField(required=False, allow_blank=True, default="")
