"""ANNUAIRE-C : CRUD admin affectations. Shape DRF ; règles = services/assignment.py."""

from rest_framework import serializers


class AssignmentCreateSerializer(serializers.Serializer):
    segment_id = serializers.UUIDField()
    start_date = serializers.DateTimeField(required=False, allow_null=True)
    end_date = serializers.DateTimeField(required=False, allow_null=True)
    position = serializers.CharField(required=False, allow_blank=True)
    position_description = serializers.CharField(required=False, allow_blank=True)


class AssignmentPatchSerializer(serializers.Serializer):
    segment_id = serializers.UUIDField(required=False)
    start_date = serializers.DateTimeField(required=False)
    end_date = serializers.DateTimeField(required=False, allow_null=True)
    position = serializers.CharField(required=False, allow_blank=True)
    position_description = serializers.CharField(required=False, allow_blank=True)
    is_active = serializers.BooleanField(required=False)
