"""Serializers appareil : spec login + JSON /me/devices (jamais push_token en GET)."""

from rest_framework import serializers


class DeviceSpecSerializer(serializers.Serializer):
    """Corps device (AUTH-11/12). Le client web stocke device_uuid dans localStorage."""

    device_uuid = serializers.CharField(max_length=128)  # ID install, obligatoire
    device_name = serializers.CharField(
        max_length=128, required=False, allow_blank=True, default=""
    )
    platform = serializers.ChoiceField(choices=["IOS", "ANDROID", "WEB", "DESKTOP", "OTHER"])
    model = serializers.CharField(max_length=128, required=False, allow_blank=True, default="")
    os_version = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    app_version = serializers.CharField(max_length=32, required=False, allow_blank=True, default="")
    push_token = serializers.CharField(required=False, allow_blank=True, default="")  # FCM / APNs
    device_fingerprint = serializers.CharField(
        max_length=255, required=False, allow_null=True, default=None
    )
    jailbreak = serializers.BooleanField(required=False, default=False)  # AUTH-32 ; WEB ignoré


class DeviceOutSerializer(serializers.Serializer):
    """GET /me/devices : jamais push_token."""

    id = serializers.UUIDField()
    device_uuid = serializers.CharField()
    device_name = serializers.CharField()
    platform = serializers.CharField()
    model = serializers.CharField()
    os_version = serializers.CharField()
    app_version = serializers.CharField()
    trusted = serializers.BooleanField()
    compromised = serializers.BooleanField()
    jailbreak = serializers.BooleanField()
    last_seen = serializers.CharField(allow_null=True)
    ip_address = serializers.CharField(allow_null=True)
    is_current = serializers.BooleanField()


class DeviceListEnvelopeSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    data = serializers.DictField()


class DeviceCurrentPatchSerializer(serializers.Serializer):
    """Heartbeat : identité = session, pas un UUID forgé."""

    push_token = serializers.CharField(required=False, allow_blank=True)
    app_version = serializers.CharField(max_length=32, required=False, allow_blank=True)
    os_version = serializers.CharField(max_length=64, required=False, allow_blank=True)
    jailbreak = serializers.BooleanField(required=False)


class DevicePatchSerializer(serializers.Serializer):
    """Rename / trusted. Pas compromised / jailbreak."""

    device_name = serializers.CharField(max_length=128, required=False, allow_blank=True)
    trusted = serializers.BooleanField(required=False)

    def validate(self, attrs):
        if "device_name" not in attrs and "trusted" not in attrs:
            raise serializers.ValidationError("Fournir device_name ou trusted.")
        return attrs


class DeviceLinkStartSerializer(serializers.Serializer):
    """POST /auth/device-link/start : DeviceSpec du waiter (ordi)."""

    device = DeviceSpecSerializer()


class DeviceLinkConfirmSerializer(serializers.Serializer):
    """POST /me/devices/link : TOTP obligatoire. backup_code → 400 métier."""

    challenge_id = serializers.UUIDField()
    otp = serializers.CharField(min_length=6, max_length=8, required=False)
    backup_code = serializers.CharField(required=False, allow_blank=True, default="")
