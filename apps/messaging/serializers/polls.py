"""MESSAGERIE-E : shapes DRF (vote sondage)."""

from rest_framework import serializers


class PollVoteSerializer(serializers.Serializer):
    option_ids = serializers.ListField(child=serializers.UUIDField(), allow_empty=False)
