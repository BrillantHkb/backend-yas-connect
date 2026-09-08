"""Serializers AUTH-D (inscription) + D05."""

from rest_framework import serializers

from apps.iam.serializers import DeviceSpecSerializer


class CheckAdSerializer(serializers.Serializer):
    """D01 : email XOR username + MDP AD. write_only : jamais renvoyé."""
    email = serializers.EmailField(max_length=254, required=False)
    username = serializers.CharField(max_length=64, required=False)
    password = serializers.CharField(
        write_only=True, min_length=1, max_length=128, trim_whitespace=False
    )

    def validate(self, attrs):
        has_email = bool(attrs.get("email"))
        has_user = bool(attrs.get("username"))
        if has_email == has_user:
            raise serializers.ValidationError("Fournir email ou username, pas les deux.")
        return attrs


class RegisterAdSerializer(serializers.Serializer):
    """D02 : deux secrets distincts — password_ad (Windows) et password (app Argon2)."""
    email = serializers.EmailField(max_length=254, required=False)
    username = serializers.CharField(max_length=64, required=False)
    password_ad = serializers.CharField(
        write_only=True, min_length=1, max_length=128, trim_whitespace=False
    )
    password = serializers.CharField(
        write_only=True, min_length=1, max_length=128, trim_whitespace=False
    )
    first_name = serializers.CharField(max_length=128)
    last_name = serializers.CharField(max_length=128)
    phone = serializers.CharField(max_length=32)
    job_title = serializers.CharField(max_length=128)
    language = serializers.CharField(max_length=8, required=False, default="fr")
    region_id = serializers.UUIDField()
    segment_id = serializers.UUIDField()
    matricule = serializers.CharField(
        max_length=32, required=False, allow_null=True, allow_blank=True, default=None
    )
    avatar_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    device = DeviceSpecSerializer()

    def validate(self, attrs):
        has_email = bool(attrs.get("email"))
        has_user = bool(attrs.get("username"))
        if has_email == has_user:
            raise serializers.ValidationError("Fournir email ou username, pas les deux.")
        return attrs


class RegisterLocalSerializer(serializers.Serializer):
    """D03 : un seul MDP app. Pas de device : pas de JWT à l’inscription locale."""
    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(
        write_only=True, min_length=1, max_length=128, trim_whitespace=False
    )
    first_name = serializers.CharField(max_length=128)
    last_name = serializers.CharField(max_length=128)
    phone = serializers.CharField(max_length=32)
    job_title = serializers.CharField(max_length=128)
    language = serializers.CharField(max_length=8, required=False, default="fr")
    region_id = serializers.UUIDField()
    segment_id = serializers.UUIDField()
    matricule = serializers.CharField(
        max_length=32, required=False, allow_null=True, allow_blank=True, default=None
    )
    avatar_id = serializers.UUIDField(required=False, allow_null=True, default=None)


class VerifyEmailSerializer(serializers.Serializer):
    """D04 : token brut (hashé en base). Jamais le hash côté client."""
    token = serializers.CharField(min_length=1)


class ResendVerificationSerializer(serializers.Serializer):
    email = serializers.EmailField()


class RejectUserSerializer(serializers.Serializer):
    """D05 : motif obligatoire, stocké en audit seulement."""
    reason = serializers.CharField(min_length=1, max_length=500)
