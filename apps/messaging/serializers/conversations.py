"""MESSAGERIE-A : shapes DRF (inbox, création, pin, mute)."""

from rest_framework import serializers


class ConversationCreateSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=["PRIVATE"])
    participant_id = serializers.UUIDField()


class ConversationPinSerializer(serializers.Serializer):
    pinned = serializers.BooleanField()


class ConversationMuteSerializer(serializers.Serializer):
    muted = serializers.BooleanField()
