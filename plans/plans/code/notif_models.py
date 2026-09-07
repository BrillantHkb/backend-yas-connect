"""
Coller dans apps/notifications/models.py.

Source : catalogues/NOTIF-catalogue-tables.md
Phase 3b : 2 tables. Dépend de iam (users).
Push tokens : devices.push_token (AUTH-E), pas de FK ici.
"""

import uuid

from django.conf import settings
from django.contrib.postgres.indexes import GinIndex
from django.db import models


class Notification(models.Model):
    """Événement in-app / push pour un destinataire."""

    class Type(models.TextChoices):
        MESSAGE_NEW = "MESSAGE_NEW"
        MESSAGE_MENTION = "MESSAGE_MENTION"
        CALL_INCOMING = "CALL_INCOMING"
        CALL_MISSED = "CALL_MISSED"
        DEVICE_NEW = "DEVICE_NEW"
        SYSTEM = "SYSTEM"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    type = models.CharField(max_length=32, choices=Type.choices, db_index=True)
    title = models.CharField(max_length=255)
    body = models.CharField(max_length=512, blank=True, default="")
    payload = models.JSONField(default=dict)
    collapse_key = models.CharField(max_length=128, blank=True, default="")
    read_at = models.DateTimeField(null=True, blank=True)
    pushed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "notifications"
        indexes = [
            models.Index(
                fields=["user", "-created_at"],
                name="notif_user_created_idx",
            ),
            models.Index(
                fields=["user", "read_at"],
                name="notif_user_read_idx",
            ),
            models.Index(fields=["collapse_key"], name="notif_collapse_idx"),
            GinIndex(fields=["payload"], name="notif_payload_gin"),
        ]


class NotificationPreference(models.Model):
    """Préférences push / sonnerie / DND — 1-1 users."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notification_preferences",
    )
    push_enabled = models.BooleanField(default=True)
    in_app_enabled = models.BooleanField(default=True)
    call_ring_enabled = models.BooleanField(default=True)
    message_preview_enabled = models.BooleanField(default=True)
    quiet_hours_enabled = models.BooleanField(default=False)
    quiet_hours_start = models.TimeField(null=True, blank=True)
    quiet_hours_end = models.TimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "notification_preferences"
