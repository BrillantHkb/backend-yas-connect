"""MESSAGERIE-E : shapes DRF (réactions)."""

from rest_framework import serializers


class ReactionSerializer(serializers.Serializer):
    emoji = serializers.CharField()
