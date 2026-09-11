"""Serializers ADMIN-A : create RH, reason, reset MDP, régions."""

from rest_framework import serializers


class AdminUserCreateSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(
        write_only=True, min_length=1, max_length=128, trim_whitespace=False
    )
    first_name = serializers.CharField(max_length=128)
    last_name = serializers.CharField(max_length=128)
    phone = serializers.CharField(max_length=32)
    job_title = serializers.CharField(max_length=128)
    region_id = serializers.UUIDField()
    segment_id = serializers.UUIDField()
    matricule = serializers.CharField(
        max_length=32, required=False, allow_null=True, allow_blank=True, default=None
    )


class AdminReasonSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, max_length=500, default="")


class AdminPasswordSerializer(serializers.Serializer):
    new_password = serializers.CharField(
        write_only=True, min_length=1, max_length=128, trim_whitespace=False
    )


class RegionCreateSerializer(serializers.Serializer):
    code = serializers.CharField()
    name = serializers.CharField()


class RegionPatchSerializer(serializers.Serializer):
    name = serializers.CharField(required=False)
    code = serializers.CharField(required=False)
