"""Serializers AUTH-A / AUTH-C : login, refresh, MFA, user public."""

from rest_framework import serializers

from apps.iam.serializers.devices import DeviceSpecSerializer


class LoginSerializer(serializers.Serializer):
    """POST /login : exactement un identifiant + password + device."""

    email = serializers.EmailField(max_length=254, required=False)
    username = serializers.CharField(max_length=64, required=False)
    password = serializers.CharField(
        write_only=True,
        min_length=1,
        max_length=128,
        trim_whitespace=False,  # MDP jamais dans la réponse
    )
    device = DeviceSpecSerializer()  # obligatoire : pas de login sans appareil

    def validate(self, attrs):
        has_email = bool(attrs.get("email"))
        has_user = bool(attrs.get("username"))
        if has_email == has_user:  # les deux ou aucun
            raise serializers.ValidationError("Fournir email ou username, pas les deux.")
        return attrs


class RefreshSerializer(serializers.Serializer):
    """POST /refresh : le clair du refresh (une fois), jamais un JWT."""

    refresh_token = serializers.CharField(write_only=True, min_length=1)


class RolePublicSerializer(serializers.Serializer):
    """Fragment OpenAPI : rôle dans le JSON user (pas d’écriture)."""

    id = serializers.UUIDField()
    code = serializers.CharField()
    name = serializers.CharField()


class PreferencesPublicSerializer(serializers.Serializer):
    """Fragment OpenAPI : user_preferences."""

    language = serializers.CharField()
    timezone = serializers.CharField()
    notification_sound = serializers.BooleanField()
    auto_download_media = serializers.BooleanField()
    read_receipts = serializers.BooleanField()
    typing_indicator = serializers.BooleanField()


class PrivacyPublicSerializer(serializers.Serializer):
    """Fragment OpenAPI : privacy_settings."""

    last_seen_visibility = serializers.CharField()
    profile_photo_visibility = serializers.CharField()
    online_status_visibility = serializers.CharField()
    read_receipts_enabled = serializers.BooleanField()
    typing_indicator_enabled = serializers.BooleanField()
    allow_calls = serializers.BooleanField()
    allow_mentions = serializers.BooleanField()
    allow_group_invites = serializers.BooleanField()


class UserPublicSerializer(serializers.Serializer):
    """Objet user du 200 login : jamais password / hash."""

    id = serializers.UUIDField()
    email = serializers.EmailField()
    username = serializers.CharField()
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    matricule = serializers.CharField(allow_null=True)
    phone = serializers.CharField(allow_null=True)
    job_title = serializers.CharField()
    status = serializers.CharField()
    language = serializers.CharField()
    timezone = serializers.CharField()
    role = RolePublicSerializer()
    region_id = serializers.UUIDField(allow_null=True)
    segment_id = serializers.UUIDField(allow_null=True)
    avatar_id = serializers.UUIDField(allow_null=True)
    preferences = PreferencesPublicSerializer(allow_null=True)
    privacy = PrivacyPublicSerializer(allow_null=True)


class TokenDataSerializer(serializers.Serializer):
    """data du 200 après MFA / refresh. backup_codes seulement à l’enroll."""

    access_token = serializers.CharField()
    refresh_token = serializers.CharField()
    token_type = serializers.CharField()
    expires_in = serializers.IntegerField()
    refresh_expires_in = serializers.IntegerField()
    user = UserPublicSerializer()
    backup_codes = serializers.ListField(
        child=serializers.CharField(), required=False
    )  # seulement au 1er verify enroll


class AuthSuccessSerializer(serializers.Serializer):
    """Enveloppe {success, data} des 200 après MFA / refresh."""

    success = serializers.BooleanField()
    data = TokenDataSerializer()


class MfaChallengeSerializer(serializers.Serializer):
    """200 facteur 1 AUTH-C : pas de JWT."""

    mfa_required = serializers.BooleanField()
    mfa_token = serializers.CharField()
    enroll = serializers.BooleanField()
    expires_in = serializers.IntegerField()
    otpauth_uri = serializers.CharField(required=False)


class MfaChallengeEnvelopeSerializer(serializers.Serializer):
    """Enveloppe {success, data} du 200 facteur 1."""

    success = serializers.BooleanField()
    data = MfaChallengeSerializer()


class MfaVerifySerializer(serializers.Serializer):
    """POST /mfa/verify : otp XOR backup_code."""

    mfa_token = serializers.CharField(min_length=16, max_length=128)
    otp = serializers.CharField(min_length=6, max_length=8, required=False)
    backup_code = serializers.CharField(min_length=8, max_length=16, required=False)

    def validate(self, attrs):
        has_otp = bool(attrs.get("otp"))
        has_b = bool(attrs.get("backup_code"))
        if has_otp == has_b:  # les deux ou aucun
            raise serializers.ValidationError("Fournir otp ou backup_code, pas les deux.")
        return attrs


class BackupRegenSerializer(serializers.Serializer):
    """Body regen : TOTP courant, pas un backup."""

    otp = serializers.CharField(min_length=6, max_length=8)
