"""MESSAGERIE-B : shapes DRF (envoi, édition). Décodage base64 délégué au service."""

from rest_framework import serializers


class MessageSendSerializer(serializers.Serializer):
    type = serializers.CharField(required=False, default="TEXT")
    encrypted_content = serializers.CharField(required=False, allow_blank=True, default="")
    parent_message_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    media_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    priority = serializers.IntegerField(required=False, default=0)
    tags = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    mentions = serializers.ListField(
        child=serializers.UUIDField(), required=False, default=list
    )
    client_message_id = serializers.CharField(required=False, allow_blank=True, default="")


class MessageEditSerializer(serializers.Serializer):
    encrypted_content = serializers.CharField()


class ConversationReadSerializer(serializers.Serializer):
    last_read_message_id = serializers.UUIDField()
