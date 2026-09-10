"""Serializers AUTH-F : accept CGU + patch wizard. Pas HasPermission."""

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from rest_framework import serializers

from apps.iam.serializers.auth import UserPublicSerializer


class TosAcceptSerializer(serializers.Serializer):
    """POST /me/tos/accept : version doit égaler YAS_TOS_VERSION."""

    version = serializers.CharField(max_length=32)


class OnboardingPatchSerializer(serializers.Serializer):
    """PATCH /me/onboarding : 3 champs optionnels (partiel)."""

    language = serializers.CharField(max_length=8, required=False)
    timezone = serializers.CharField(max_length=64, required=False)
    notification_sound = serializers.BooleanField(required=False)

    def validate_timezone(self, value):
        try:
            ZoneInfo(value)  # IANA, ex. Africa/Lome
        except ZoneInfoNotFoundError as exc:
            raise serializers.ValidationError("Fuseau horaire invalide.") from exc
        return value


class GatesSerializer(serializers.Serializer):
    """Fragment GET /me.gates."""

    tos_required = serializers.BooleanField()
    tos_current_version = serializers.CharField()
    onboarding_required = serializers.BooleanField()
    first_login_at = serializers.CharField(allow_null=True)


class MeDataSerializer(serializers.Serializer):
    user = UserPublicSerializer()
    gates = GatesSerializer()


class MeEnvelopeSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    data = MeDataSerializer()


class TosPublicSerializer(serializers.Serializer):
    version = serializers.CharField()
    url = serializers.CharField()


class TosEnvelopeSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    data = TosPublicSerializer()


class OnboardingDataSerializer(serializers.Serializer):
    language = serializers.CharField()
    timezone = serializers.CharField()
    notification_sound = serializers.BooleanField()


class OnboardingEnvelopeSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    data = OnboardingDataSerializer()
