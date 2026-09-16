"""MESSAGERIE-A/C : shapes DRF (inbox, création privé/groupe, pin, mute, membres, réglages)."""

from rest_framework import serializers


class ConversationCreateSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=["PRIVATE", "GROUP"])
    participant_id = serializers.UUIDField(required=False)
    title = serializers.CharField(required=False, allow_blank=True, default="")
    member_ids = serializers.ListField(
        child=serializers.UUIDField(), required=False, default=list
    )
    visibility = serializers.ChoiceField(
        choices=["PRIVATE", "PUBLIC"], required=False, default="PRIVATE"
    )

    def validate(self, attrs):
        if attrs["type"] == "PRIVATE":
            if not attrs.get("participant_id"):
                raise serializers.ValidationError(
                    {"participant_id": "Requis pour un fil PRIVATE."}
                )
        elif not attrs.get("title", "").strip():
            raise serializers.ValidationError({"title": "Requis pour un GROUP."})
        return attrs


class ConversationPinSerializer(serializers.Serializer):
    pinned = serializers.BooleanField()


class ConversationMuteSerializer(serializers.Serializer):
    muted = serializers.BooleanField()


class ConversationUpdateSerializer(serializers.Serializer):
    title = serializers.CharField(required=False, allow_blank=True)
    description = serializers.CharField(required=False, allow_blank=True)
    avatar_media_id = serializers.UUIDField(required=False, allow_null=True)


class GroupSettingsSerializer(serializers.Serializer):
    visibility = serializers.ChoiceField(choices=["PRIVATE", "PUBLIC"], required=False)
    locked = serializers.BooleanField(required=False)
    max_members = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    welcome_message = serializers.CharField(required=False, allow_blank=True)
    rules = serializers.CharField(required=False, allow_blank=True)


class MemberAddSerializer(serializers.Serializer):
    user_id = serializers.UUIDField()
    role = serializers.ChoiceField(
        choices=["MEMBER", "READ_ONLY"], required=False, default="MEMBER"
    )


class MemberUpdateSerializer(serializers.Serializer):
    role = serializers.ChoiceField(
        choices=["OWNER", "ADMIN", "MEMBER", "READ_ONLY"], required=False
    )
    username = serializers.CharField(required=False, allow_blank=True)
