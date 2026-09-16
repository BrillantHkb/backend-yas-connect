"""MESSAGERIE-F : shapes DRF (signalement)."""

from rest_framework import serializers


class ReportCreateSerializer(serializers.Serializer):
    reason = serializers.CharField()


class ReportReviewSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=["REVIEWED", "DISMISSED"])
    note = serializers.CharField(required=False, allow_blank=True, default="")
