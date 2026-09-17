"""MEDIA-E : shapes DRF (GED)."""

from rest_framework import serializers


class DocumentCreateSerializer(serializers.Serializer):
    upload_id = serializers.UUIDField()
    title = serializers.CharField()
    category = serializers.CharField(required=False, allow_blank=True, default="")
    confidential = serializers.BooleanField(required=False, default=False)


class DocumentUpdateSerializer(serializers.Serializer):
    title = serializers.CharField(required=False)
    category = serializers.CharField(required=False, allow_blank=True)
    confidential = serializers.BooleanField(required=False)
    owner_id = serializers.UUIDField(required=False, allow_null=True)


class DocumentVersionCreateSerializer(serializers.Serializer):
    upload_id = serializers.UUIDField()
    comment = serializers.CharField(required=False, allow_blank=True, default="")
