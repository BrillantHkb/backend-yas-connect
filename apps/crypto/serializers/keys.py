"""CRYPTO-A : shape DRF. Décodage base64 délégué au service (mêmes codes d'erreur)."""

from rest_framework import serializers


class IdentitySerializer(serializers.Serializer):
    registration_id = serializers.IntegerField()
    identity_public_key = serializers.CharField()


class SignedPrekeySerializer(serializers.Serializer):
    key_id = serializers.IntegerField()
    public_key = serializers.CharField()
    signature = serializers.CharField()


class OneTimePrekeyEntrySerializer(serializers.Serializer):
    key_id = serializers.IntegerField()
    public_key = serializers.CharField()


class OneTimePrekeysBatchSerializer(serializers.Serializer):
    keys = OneTimePrekeyEntrySerializer(many=True)
