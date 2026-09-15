"""Serializers ANNUAIRE-A : enveloppe GET /users (people-picker)."""

from rest_framework import serializers


class SearchSegmentMiniSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    code = serializers.CharField()
    name = serializers.CharField()


class SearchOrgSerializer(serializers.Serializer):
    segment = SearchSegmentMiniSerializer()


class UserSearchHitSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    display_name = serializers.CharField()
    username = serializers.CharField()
    job_title = serializers.CharField()
    avatar_url = serializers.CharField(allow_null=True)
    org = SearchOrgSerializer(allow_null=True)
    status = serializers.CharField(allow_null=True)
    badge = serializers.CharField(allow_null=True)


class UserSearchDataSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    results = UserSearchHitSerializer(many=True)


class UserSearchEnvelopeSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    data = UserSearchDataSerializer()
