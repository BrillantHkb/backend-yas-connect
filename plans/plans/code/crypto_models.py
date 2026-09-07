"""
Coller dans apps/crypto/models.py.

Source : catalogues/CRYPTO-catalogue-tables.md
Phase 3c : 4 tables. Dépend de iam (users, devices).
conversation_id : UUID sans FK (module Messagerie).
"""

import uuid

from django.conf import settings
from django.db import models


class IdentityKey(models.Model):
    """Clé d'identité Signal publique — 1 / appareil. Jamais de privée."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="identity_keys",
    )
    device = models.OneToOneField(
        "iam.Device",
        on_delete=models.CASCADE,
        related_name="identity_key",
    )
    registration_id = models.IntegerField()
    identity_public_key = models.BinaryField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "identity_keys"


class SignedPreKey(models.Model):
    """Signed prekey publique, rotation par appareil."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    device = models.ForeignKey(
        "iam.Device",
        on_delete=models.CASCADE,
        related_name="signed_prekeys",
    )
    key_id = models.IntegerField()
    public_key = models.BinaryField()
    signature = models.BinaryField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "signed_prekeys"
        unique_together = [("device", "key_id")]
        indexes = [
            models.Index(
                fields=["device", "-created_at"],
                name="spk_device_created_idx",
            ),
        ]


class OneTimePreKey(models.Model):
    """One-time prekey ; consommée à la lecture du bundle."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    device = models.ForeignKey(
        "iam.Device",
        on_delete=models.CASCADE,
        related_name="one_time_prekeys",
    )
    key_id = models.IntegerField()
    public_key = models.BinaryField()
    consumed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "one_time_prekeys"
        unique_together = [("device", "key_id")]
        indexes = [
            models.Index(
                fields=["device"],
                name="otpk_device_available_idx",
                condition=models.Q(consumed_at__isnull=True),
            ),
        ]


class ConversationKey(models.Model):
    """Clé cloud GROUP/AI wrappée at-rest. Pas de ligne PRIVATE."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation_id = models.UUIDField()  # Messagerie — pas de FK
    version = models.IntegerField(default=1)
    algorithm = models.CharField(max_length=32, default="AES-256-GCM")
    wrapped_key = models.BinaryField()
    is_current = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "conversation_keys"
        unique_together = [("conversation_id", "version")]
        indexes = [
            models.Index(
                fields=["conversation_id"],
                name="conv_keys_conv_idx",
            ),
        ]
