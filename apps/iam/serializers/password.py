"""Serializers AUTH-G : change JWT + forgot / verify / reset publics."""

from rest_framework import serializers


def _reject_channel(data):
    """AUTH-47 : pas EMAIL/SMS/APPEL. Champ interdit → 400 validation."""
    if isinstance(data, dict) and "channel" in data:
        raise serializers.ValidationError({"channel": "Champ interdit."})


class PasswordChangeSerializer(serializers.Serializer):
    """POST /me/password. logout_others défaut true."""

    old_password = serializers.CharField(write_only=True, max_length=128, trim_whitespace=False)
    new_password = serializers.CharField(write_only=True, max_length=128, trim_whitespace=False)
    logout_others = serializers.BooleanField(required=False, default=True)


class PasswordForgotSerializer(serializers.Serializer):
    """POST /auth/password/forgot : email XOR username."""

    email = serializers.EmailField(max_length=254, required=False)
    username = serializers.CharField(max_length=64, required=False)

    def to_internal_value(self, data):
        _reject_channel(data)
        return super().to_internal_value(data)

    def validate(self, attrs):
        has_email = bool(attrs.get("email"))
        has_user = bool(attrs.get("username"))
        if has_email == has_user:
            raise serializers.ValidationError("Fournir email ou username, pas les deux.")
        return attrs


class PasswordResetVerifySerializer(serializers.Serializer):
    """POST /auth/password/reset/verify : ident + otp XOR backup."""

    email = serializers.EmailField(max_length=254, required=False)
    username = serializers.CharField(max_length=64, required=False)
    otp = serializers.CharField(min_length=6, max_length=8, required=False)
    backup_code = serializers.CharField(min_length=8, max_length=16, required=False)

    def to_internal_value(self, data):
        _reject_channel(data)
        return super().to_internal_value(data)

    def validate(self, attrs):
        has_email = bool(attrs.get("email"))
        has_user = bool(attrs.get("username"))
        if has_email == has_user:
            raise serializers.ValidationError("Fournir email ou username, pas les deux.")
        has_otp = bool(attrs.get("otp"))
        has_b = bool(attrs.get("backup_code"))
        if has_otp == has_b:
            raise serializers.ValidationError("Fournir otp ou backup_code, pas les deux.")
        return attrs


class PasswordResetSerializer(serializers.Serializer):
    """POST /auth/password/reset. logout_all défaut true."""

    reset_token = serializers.CharField(write_only=True, min_length=16)
    new_password = serializers.CharField(write_only=True, max_length=128, trim_whitespace=False)
    logout_all = serializers.BooleanField(required=False, default=True)


class PasswordResetTicketSerializer(serializers.Serializer):
    reset_token = serializers.CharField()
    expires_in = serializers.IntegerField()


class PasswordResetTicketEnvelopeSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    data = PasswordResetTicketSerializer()


class PasswordForgotEnvelopeSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    message = serializers.CharField()


class PasswordOkEnvelopeSerializer(serializers.Serializer):
    success = serializers.BooleanField()
