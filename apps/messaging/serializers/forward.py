"""MESSAGERIE-E : shapes DRF (transfert)."""

from rest_framework import serializers


class ForwardSerializer(serializers.Serializer):
    conversation_id = serializers.UUIDField()
    encrypted_content = serializers.CharField(required=False, allow_blank=True, default="")
