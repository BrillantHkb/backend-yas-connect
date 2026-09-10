"""Serializers AUTH-R : rôles, permissions, matrice, assignation."""

from rest_framework import serializers


class RoleCreateSerializer(serializers.Serializer):
    code = serializers.CharField()
    name = serializers.CharField()
    description = serializers.CharField(required=False, allow_blank=True, default="")
    level = serializers.IntegerField(required=False)


class RolePatchSerializer(serializers.Serializer):
    name = serializers.CharField(required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    level = serializers.IntegerField(required=False)


class PermissionCreateSerializer(serializers.Serializer):
    module = serializers.CharField()
    resource = serializers.CharField()
    action = serializers.CharField()
    name = serializers.CharField()
    description = serializers.CharField(required=False, allow_blank=True, default="")


class PermissionCodesSerializer(serializers.Serializer):
    permission_codes = serializers.ListField(child=serializers.CharField(), allow_empty=True)


class UserRoleSerializer(serializers.Serializer):
    role_code = serializers.CharField()


class RoleOutSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    code = serializers.CharField()
    name = serializers.CharField()
    description = serializers.CharField()
    level = serializers.IntegerField()
    is_system = serializers.BooleanField()
    users_count = serializers.IntegerField()
    permissions_count = serializers.IntegerField()
    permission_codes = serializers.ListField(child=serializers.CharField(), required=False)
    created_at = serializers.CharField()
    updated_at = serializers.CharField()
