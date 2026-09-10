"""Serializers AUTH-I : historique, change email, unlock admin. Jamais de hash."""

from rest_framework import serializers


class LoginHistoryOutSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    created_at = serializers.CharField(allow_null=True)
    success = serializers.BooleanField()
    suspicious = serializers.BooleanField()
    ip_address = serializers.CharField(allow_null=True)
    country = serializers.CharField(allow_null=True)
    city = serializers.CharField(allow_null=True)
    device_id = serializers.UUIDField(allow_null=True)
    device_name = serializers.CharField(allow_null=True)
    platform = serializers.CharField(allow_null=True)
    browser = serializers.CharField(allow_null=True)
    login_method = serializers.CharField()
    failure_reason = serializers.CharField(allow_null=True)


class LoginHistoryListDataSerializer(serializers.Serializer):
    logins = LoginHistoryOutSerializer(many=True)


class LoginHistoryEnvelopeSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    data = LoginHistoryListDataSerializer()


class EmailChangeSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)


class EmailChangeEnvelopeSerializer(serializers.Serializer):
    success = serializers.BooleanField()


class EmailVerifySerializer(serializers.Serializer):
    token = serializers.CharField(min_length=1)


class UnlockSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, default="", max_length=500)


class UnlockEnvelopeSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    data = serializers.DictField()
