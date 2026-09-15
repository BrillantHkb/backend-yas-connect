"""ANNUAIRE-D : CRUD skills/certifs. Shape DRF ; règles = services/competences.py."""

from rest_framework import serializers


class SkillCreateSerializer(serializers.Serializer):
    skill_name = serializers.CharField()
    level = serializers.IntegerField(required=False, allow_null=True)


class SkillPatchSerializer(serializers.Serializer):
    skill_name = serializers.CharField(required=False)
    level = serializers.IntegerField(required=False, allow_null=True)


class CertificationCreateSerializer(serializers.Serializer):
    certification_name = serializers.CharField()
    issued_at = serializers.DateField(required=False, allow_null=True)
    document_id = serializers.UUIDField(required=False, allow_null=True)


class CertificationPatchSerializer(serializers.Serializer):
    certification_name = serializers.CharField(required=False)
    issued_at = serializers.DateField(required=False, allow_null=True)
    document_id = serializers.UUIDField(required=False, allow_null=True)
