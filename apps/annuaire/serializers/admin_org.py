"""ANNUAIRE-B : CRUD admin segment_types / segments. Shape DRF ; règles métier = org_tree.py."""

from rest_framework import serializers


class SegmentTypeCreateSerializer(serializers.Serializer):
    code = serializers.CharField()
    name = serializers.CharField()
    level = serializers.IntegerField(required=False, default=0)
    description = serializers.CharField(required=False, allow_blank=True)


class SegmentTypePatchSerializer(serializers.Serializer):
    code = serializers.CharField(required=False)
    name = serializers.CharField(required=False)
    level = serializers.IntegerField(required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    is_active = serializers.BooleanField(required=False)


class SegmentCreateSerializer(serializers.Serializer):
    code = serializers.CharField()
    name = serializers.CharField()
    description = serializers.CharField(required=False, allow_blank=True)
    segment_type_id = serializers.UUIDField(required=False, allow_null=True)
    parent_segment_id = serializers.UUIDField(required=False, allow_null=True)
    responsable_id = serializers.UUIDField(required=False, allow_null=True)
    is_active = serializers.BooleanField(required=False, default=True)


class SegmentPatchSerializer(serializers.Serializer):
    code = serializers.CharField(required=False)
    name = serializers.CharField(required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    segment_type_id = serializers.UUIDField(required=False, allow_null=True)
    parent_segment_id = serializers.UUIDField(required=False, allow_null=True)
    responsable_id = serializers.UUIDField(required=False, allow_null=True)
    is_active = serializers.BooleanField(required=False)
