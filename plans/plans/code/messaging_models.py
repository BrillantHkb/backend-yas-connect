"""
Coller dans apps/messaging/models.py.

Source : catalogues/MESSAGERIE-catalogue-tables.md
Phase 3 : 18 tables. Dépend de iam (users, devices) et media (media_files).
Pas de PostGIS : GPS dans encrypted_content (CRYPTO-00).
call_id : UUID sans FK (module Appels).
"""

import uuid

from django.conf import settings
from django.contrib.postgres.indexes import GinIndex
from django.db import models


class Conversation(models.Model):
    """Fil de discussion (privé, groupe, IA)."""

    class Type(models.TextChoices):
        PRIVATE = "PRIVATE"
        GROUP = "GROUP"
        AI = "AI"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation_uuid = models.UUIDField(unique=True, default=uuid.uuid4, editable=False)
    type = models.CharField(max_length=16, choices=Type.choices)
    title = models.CharField(max_length=255, blank=True, default="")
    description = models.TextField(blank=True, default="")
    encrypted = models.BooleanField(default=False)  # PRIVATE: toujours True (CRYPTO-00)
    last_message_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_message = models.ForeignKey(
        "Message",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    avatar_media = models.ForeignKey(
        "media.MediaFile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="conversation_avatars",
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="owned_conversations",
    )

    class Meta:
        db_table = "conversations"
        indexes = [
            models.Index(fields=["-last_message_at"], name="conv_last_msg_at_idx"),
            models.Index(fields=["type"], name="conv_type_idx"),
        ]


class ConversationMember(models.Model):
    """Appartenance user ↔ conversation."""

    class Role(models.TextChoices):
        OWNER = "OWNER"
        ADMIN = "ADMIN"
        MEMBER = "MEMBER"
        READ_ONLY = "READ_ONLY"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    username = models.CharField(max_length=100, blank=True, default="")
    role = models.CharField(max_length=16, choices=Role.choices)
    unread_count = models.IntegerField(default=0)
    left_at = models.DateTimeField(null=True, blank=True)
    active = models.BooleanField(default=True)
    archived = models.BooleanField(default=False)
    pinned = models.BooleanField(default=False)
    joined_at = models.DateTimeField(auto_now_add=True)
    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name="members"
    )
    last_read_message = models.ForeignKey(
        "Message",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="conversation_memberships",
    )

    class Meta:
        db_table = "conversation_members"
        unique_together = [("conversation", "user")]
        indexes = [
            models.Index(
                fields=["user", "active", "-joined_at"],
                name="conv_memb_user_active_idx",
            ),
            models.Index(fields=["conversation", "active"], name="conv_memb_conv_active_idx"),
        ]


class Message(models.Model):
    """Message chiffré ; pas de colonne content en clair."""

    class Type(models.TextChoices):
        TEXT = "TEXT"
        IMAGE = "IMAGE"
        VIDEO = "VIDEO"
        AUDIO = "AUDIO"
        DOCUMENT = "DOCUMENT"
        GIF = "GIF"
        LOCATION = "LOCATION"
        POLL = "POLL"
        SYSTEM = "SYSTEM"
        CALL = "CALL"
        AI = "AI"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    type = models.CharField(max_length=16, choices=Type.choices)
    encrypted_content = models.BinaryField(null=True, blank=True)
    mentions = models.JSONField(default=list, blank=True)
    tags = models.JSONField(default=list, blank=True)
    forwarded = models.BooleanField(default=False)
    edited = models.BooleanField(default=False)
    deleted = models.BooleanField(default=False)
    pinned = models.BooleanField(default=False)
    priority = models.SmallIntegerField(default=0)
    ai_generated = models.BooleanField(default=False)
    metadata = models.JSONField(default=dict, blank=True)
    sent_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    media = models.ForeignKey(
        "media.MediaFile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="messages",
    )
    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name="messages"
    )
    parent_message = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="replies",
    )
    poll = models.ForeignKey(
        "MessagePoll",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="messages_via_poll_id",
    )
    call_id = models.UUIDField(null=True, blank=True)  # module Appels — pas de FK
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sent_messages",
    )

    class Meta:
        db_table = "messages"
        indexes = [
            models.Index(
                fields=["conversation", "-sent_at"],
                name="msg_conv_sent_at_idx",
            ),
            models.Index(fields=["sender", "-sent_at"], name="msg_sender_sent_at_idx"),
            models.Index(fields=["type"], name="msg_type_idx"),
            models.Index(fields=["call_id"], name="msg_call_id_idx"),
            GinIndex(fields=["mentions"], name="msg_mentions_gin"),
            GinIndex(fields=["tags"], name="msg_tags_gin"),
            GinIndex(fields=["metadata"], name="msg_metadata_gin"),
        ]


class MessageRead(models.Model):
    """Accusés livré / lu par user et device."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    delivered_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name="reads")
    device = models.ForeignKey(
        "iam.Device",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="message_reads",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="message_reads",
    )

    class Meta:
        db_table = "message_reads"
        constraints = [
            models.UniqueConstraint(
                fields=["message", "user", "device"],
                name="msg_reads_msg_user_dev_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "-read_at"], name="msg_reads_user_read_idx"),
        ]


class MessageReaction(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    emoji = models.CharField(max_length=20)
    created_at = models.DateTimeField(auto_now_add=True)
    message = models.ForeignKey(
        Message, on_delete=models.CASCADE, related_name="reactions"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="message_reactions",
    )

    class Meta:
        db_table = "message_reactions"
        unique_together = [("message", "user", "emoji")]


class MessageEdit(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    previous_encrypted_content = models.BinaryField()
    edited_at = models.DateTimeField()
    message = models.ForeignKey(
        Message, on_delete=models.CASCADE, related_name="edits"
    )
    edited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="message_edits",
    )

    class Meta:
        db_table = "message_edits"
        indexes = [
            models.Index(fields=["message", "-edited_at"], name="msg_edits_msg_at_idx"),
        ]


class MessageDelete(models.Model):
    class DeleteScope(models.TextChoices):
        SELF = "SELF"
        EVERYONE = "EVERYONE"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    delete_scope = models.CharField(max_length=16, choices=DeleteScope.choices)
    deleted_at = models.DateTimeField()
    message = models.ForeignKey(
        Message, on_delete=models.CASCADE, related_name="deletes"
    )
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="message_deletes",
    )

    class Meta:
        db_table = "message_deletes"


class MessageForward(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    original_message = models.ForeignKey(
        Message,
        on_delete=models.CASCADE,
        related_name="forwards_as_original",
    )
    new_message = models.ForeignKey(
        Message,
        on_delete=models.CASCADE,
        related_name="forwards_as_new",
    )
    forwarded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="message_forwards",
    )

    class Meta:
        db_table = "message_forwards"


class PinnedMessage(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    pinned_at = models.DateTimeField()
    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name="pinned_messages"
    )
    message = models.ForeignKey(
        Message, on_delete=models.CASCADE, related_name="pins"
    )
    pinned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pinned_messages",
    )

    class Meta:
        db_table = "pinned_messages"
        unique_together = [("conversation", "message")]


class MessageMention(models.Model):
    """Source relationnelle des @mentions (notifications)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    message = models.ForeignKey(
        Message, on_delete=models.CASCADE, related_name="mention_rows"
    )
    mentioned_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="message_mentions",
    )

    class Meta:
        db_table = "message_mentions"
        unique_together = [("message", "mentioned_user")]
        indexes = [
            models.Index(fields=["mentioned_user", "-created_at"], name="msg_ment_user_at_idx"),
        ]


class MessagePoll(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    question = models.TextField()
    multiple_choices = models.BooleanField(default=False)
    closed_at = models.DateTimeField(null=True, blank=True)
    message = models.OneToOneField(
        Message, on_delete=models.CASCADE, related_name="poll_detail"
    )
    device = models.ForeignKey(
        "iam.Device",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_polls",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_polls",
    )

    class Meta:
        db_table = "message_polls"


class PollOption(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    label = models.TextField()
    vote_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    poll = models.ForeignKey(
        MessagePoll, on_delete=models.CASCADE, related_name="options"
    )

    class Meta:
        db_table = "poll_options"


class PollVote(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    poll_option = models.ForeignKey(
        PollOption, on_delete=models.CASCADE, related_name="votes"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="poll_votes",
    )

    class Meta:
        db_table = "poll_votes"
        unique_together = [("poll_option", "user")]


class BlockedUser(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reason = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    blocked = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="blocked_by",
    )
    blocker = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="blocked_users",
    )

    class Meta:
        db_table = "blocked_users"
        unique_together = [("blocker", "blocked")]


class ReportedMessage(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING"
        REVIEWED = "REVIEWED"
        DISMISSED = "DISMISSED"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reason = models.TextField()
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PENDING
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    message = models.ForeignKey(
        Message, on_delete=models.CASCADE, related_name="reports"
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_message_reports",
    )
    reported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="submitted_message_reports",
    )

    class Meta:
        db_table = "reported_messages"
        indexes = [
            models.Index(fields=["status", "-created_at"], name="msg_rpt_status_at_idx"),
        ]


class MessageBookmark(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    note = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    message = models.ForeignKey(
        Message, on_delete=models.CASCADE, related_name="bookmarks"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="message_bookmarks",
    )

    class Meta:
        db_table = "message_bookmarks"
        unique_together = [("user", "message")]


class ArchivedConversation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name="archives"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="archived_conversations",
    )

    class Meta:
        db_table = "archived_conversations"
        unique_together = [("user", "conversation")]


class ConversationSetting(models.Model):
    """Préférences par user sur une conversation."""

    class Visibility(models.TextChoices):
        PRIVATE = "PRIVATE"
        PUBLIC = "PUBLIC"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    muted = models.BooleanField(default=False)
    visibility = models.CharField(
        max_length=16, choices=Visibility.choices, default=Visibility.PRIVATE
    )
    locked = models.BooleanField(default=False)
    max_members = models.IntegerField(null=True, blank=True)
    custom_settings = models.JSONField(default=dict, blank=True)
    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name="settings"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="conversation_settings",
    )

    class Meta:
        db_table = "conversation_settings"
        unique_together = [("conversation", "user")]
        indexes = [
            GinIndex(fields=["custom_settings"], name="conv_sett_custom_gin"),
        ]
