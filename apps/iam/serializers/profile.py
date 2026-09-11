"""Serializers PROF-A : PATCH /me + OpenAPI fiche."""

from rest_framework import serializers

from apps.iam.serializers.auth import PreferencesPublicSerializer, PrivacyPublicSerializer
from apps.iam.serializers.prefs import EditableSerializer


class ProfilePatchSerializer(serializers.Serializer):
    """Body PATCH /me : au moins un champ. Interdits contrôlés sur request.data."""

    first_name = serializers.CharField(max_length=128, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=128, required=False, allow_blank=True)
    username = serializers.RegexField(r"^[a-z0-9._]+$", min_length=3, max_length=64, required=False)
    phone = serializers.CharField(max_length=32, required=False, allow_null=True, allow_blank=True)
    job_title = serializers.CharField(max_length=128, required=False, allow_blank=True)

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("Aucun champ à modifier.")
        return attrs


class RegionMiniSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    code = serializers.CharField()
    name = serializers.CharField()


class ColleagueRoleSerializer(serializers.Serializer):
    code = serializers.CharField()
    name = serializers.CharField()


class ProfileMeUserSerializer(serializers.Serializer):
    """Objet user GET /me : pas de rôle."""

    id = serializers.UUIDField()
    display_name = serializers.CharField()
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    username = serializers.CharField()
    email = serializers.EmailField()
    email_pending = serializers.EmailField(allow_null=True)
    phone = serializers.CharField(allow_null=True)
    matricule = serializers.CharField(allow_null=True)
    job_title = serializers.CharField()
    status = serializers.CharField()
    language = serializers.CharField()
    timezone = serializers.CharField()
    segment_id = serializers.UUIDField(allow_null=True)
    avatar_id = serializers.UUIDField(allow_null=True)
    avatar_url = serializers.CharField(allow_null=True)
    region = RegionMiniSerializer(allow_null=True)
    org = serializers.JSONField(allow_null=True)
    last_seen = serializers.CharField(allow_null=True)
    preferences = PreferencesPublicSerializer(allow_null=True)
    privacy = PrivacyPublicSerializer(allow_null=True)
    editable = EditableSerializer()


class ColleagueUserSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    display_name = serializers.CharField()
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    username = serializers.CharField()
    email = serializers.EmailField()
    phone = serializers.CharField(allow_null=True)
    matricule = serializers.CharField(allow_null=True)
    job_title = serializers.CharField()
    status = serializers.CharField(allow_null=True)
    language = serializers.CharField()
    timezone = serializers.CharField()
    segment_id = serializers.UUIDField(allow_null=True)
    avatar_id = serializers.UUIDField(allow_null=True)
    avatar_url = serializers.CharField(allow_null=True)
    region = RegionMiniSerializer(allow_null=True)
    org = serializers.JSONField(allow_null=True)
    last_seen = serializers.CharField(allow_null=True)
    role = ColleagueRoleSerializer()


class ColleagueDataSerializer(serializers.Serializer):
    user = ColleagueUserSerializer()


class ColleagueEnvelopeSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    data = ColleagueDataSerializer()


class AvatarDataSerializer(serializers.Serializer):
    avatar_id = serializers.UUIDField()
    avatar_url = serializers.CharField(allow_null=True)


class AvatarEnvelopeSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    data = AvatarDataSerializer()
