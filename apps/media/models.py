"""
Coller dans apps/media/models.py.

Source : catalogues/MEDIA-catalogue-tables.md
AUTH-01 : 10 tables créées, 0 ligne (users.avatar_id NULL jusqu’à PROF-A).
"""

import uuid

from django.conf import settings
from django.contrib.postgres.indexes import GinIndex
from django.db import models


class MediaFile(models.Model):
    """Fichier stocké (avatar, PJ certif, chat, GED). Aucun INSERT au login."""

    class MediaType(models.TextChoices):
        IMAGE = "IMAGE"
        VIDEO = "VIDEO"
        AUDIO = "AUDIO"
        DOCUMENT = "DOCUMENT"
        OTHER = "OTHER"

    class ScanStatus(models.TextChoices):
        PENDING = "PENDING"
        CLEAN = "CLEAN"
        INFECTED = "INFECTED"
        SKIPPED = "SKIPPED"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="media_files",
    )
    storage_path = models.TextField()
    original_name = models.CharField(max_length=255, blank=True, default="")
    mime_type = models.CharField(max_length=100, blank=True, default="")
    media_type = models.CharField(
        max_length=16, choices=MediaType.choices, default=MediaType.OTHER
    )
    size_bytes = models.BigIntegerField(default=0)
    checksum = models.CharField(
        max_length=128, null=True, blank=True, unique=True
    )  # NULL si empreinte inconnue
    bucket_name = models.CharField(max_length=100, blank=True, default="")
    encrypted = models.BooleanField(default=False)
    compressed = models.BooleanField(default=False)
    virus_scanned = models.BooleanField(default=False)
    scan_status = models.CharField(
        max_length=20, choices=ScanStatus.choices, default=ScanStatus.PENDING
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "media_files"
        indexes = [
            models.Index(fields=["owner", "-created_at"], name="media_owner_created_idx"),
            models.Index(fields=["scan_status"], name="media_scan_status_idx"),
            models.Index(fields=["media_type"], name="media_type_idx"),
        ]


class MediaMetadata(models.Model):
    """EXIF / métadonnées techniques communes (1:1 media_files)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    media = models.OneToOneField(
        MediaFile, on_delete=models.CASCADE, related_name="metadata_detail"
    )
    width = models.IntegerField(null=True, blank=True)
    height = models.IntegerField(null=True, blank=True)
    duration_seconds = models.IntegerField(null=True, blank=True)
    codec = models.CharField(max_length=50, blank=True, default="")
    latitude = models.DecimalField(
        max_digits=10, decimal_places=7, null=True, blank=True
    )
    longitude = models.DecimalField(
        max_digits=10, decimal_places=7, null=True, blank=True
    )
    captured_at = models.DateTimeField(null=True, blank=True)
    device_model = models.CharField(max_length=100, blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "media_metadata"
        indexes = [
            GinIndex(fields=["metadata"], name="media_meta_json_gin"),
        ]


class Image(models.Model):
    """Dérivés image (thumbnail, optimisé)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    media = models.OneToOneField(
        MediaFile, on_delete=models.CASCADE, related_name="image_detail"
    )
    thumbnail_path = models.TextField(blank=True, default="")
    optimized_path = models.TextField(blank=True, default="")
    original_resolution = models.CharField(max_length=50, blank=True, default="")
    format = models.CharField(max_length=20, blank=True, default="")
    quality = models.SmallIntegerField(default=0)
    annotated = models.BooleanField(default=False)
    blurred = models.BooleanField(default=False)

    class Meta:
        db_table = "images"


class Video(models.Model):
    """Vidéo et pipeline transcodage."""

    class TranscodingStatus(models.TextChoices):
        PENDING = "PENDING"
        PROCESSING = "PROCESSING"
        READY = "READY"
        FAILED = "FAILED"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    media = models.OneToOneField(
        MediaFile, on_delete=models.CASCADE, related_name="video_detail"
    )
    duration_seconds = models.IntegerField(default=0)
    resolution = models.CharField(max_length=30, blank=True, default="")
    codec = models.CharField(max_length=50, blank=True, default="")
    thumbnail_path = models.TextField(blank=True, default="")
    streaming_ready = models.BooleanField(default=False)
    transcoding_status = models.CharField(
        max_length=30,
        choices=TranscodingStatus.choices,
        default=TranscodingStatus.PENDING,
    )

    class Meta:
        db_table = "videos"
        indexes = [
            models.Index(fields=["transcoding_status"], name="videos_transcode_idx"),
        ]


class AudioMessage(models.Model):
    """Message vocal (waveform, STT)."""

    class TranscriptionStatus(models.TextChoices):
        PENDING = "PENDING"
        PROCESSING = "PROCESSING"
        DONE = "DONE"
        FAILED = "FAILED"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    media = models.OneToOneField(
        MediaFile, on_delete=models.CASCADE, related_name="audio_detail"
    )
    duration_seconds = models.IntegerField(default=0)
    waveform = models.JSONField(default=list, blank=True)
    codec = models.CharField(max_length=30, blank=True, default="")
    transcription_status = models.CharField(
        max_length=30,
        choices=TranscriptionStatus.choices,
        default=TranscriptionStatus.PENDING,
    )

    class Meta:
        db_table = "audio_messages"
        indexes = [
            GinIndex(fields=["waveform"], name="audio_msg_waveform_gin"),
            models.Index(
                fields=["transcription_status"], name="audio_msg_transcript_idx"
            ),
        ]


class VoiceTranscription(models.Model):
    """Transcription STT d’un vocal."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    audio = models.ForeignKey(
        AudioMessage, on_delete=models.CASCADE, related_name="transcriptions"
    )
    language = models.CharField(max_length=10, blank=True, default="")
    text = models.TextField()
    confidence = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    model_used = models.CharField(max_length=100, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "voice_transcriptions"
        indexes = [
            models.Index(fields=["audio", "-created_at"], name="voice_tr_audio_at_idx"),
        ]


class Document(models.Model):
    """Document GED (métier) lié à un media_files."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    media = models.OneToOneField(
        MediaFile, on_delete=models.CASCADE, related_name="document_detail"
    )
    title = models.CharField(max_length=255, blank=True, default="")
    category = models.CharField(max_length=100, blank=True, default="")
    confidential = models.BooleanField(default=False)
    version = models.IntegerField(default=1)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="owned_documents",
    )
    extracted_text = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "documents"
        indexes = [
            models.Index(fields=["category"], name="documents_category_idx"),
            models.Index(fields=["owner", "-created_at"], name="documents_owner_at_idx"),
        ]


class DocumentVersion(models.Model):
    """Version immuable d’un document (blob = media_files)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(
        Document, on_delete=models.CASCADE, related_name="versions"
    )
    version_number = models.IntegerField()
    media = models.ForeignKey(
        MediaFile, on_delete=models.CASCADE, related_name="document_versions"
    )
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="document_version_changes",
    )
    comment = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "document_versions"
        unique_together = [("document", "version_number")]
        indexes = [
            models.Index(fields=["media"], name="doc_ver_media_idx"),
        ]


class MediaAccessLog(models.Model):
    """Journal d’accès append-only."""

    class Action(models.TextChoices):
        VIEW = "VIEW"
        DOWNLOAD = "DOWNLOAD"
        DELETE = "DELETE"
        SHARE = "SHARE"

    id = models.BigAutoField(primary_key=True)
    media = models.ForeignKey(
        MediaFile, on_delete=models.CASCADE, related_name="access_logs"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="media_access_logs",
    )
    action = models.CharField(max_length=20, choices=Action.choices)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    device = models.ForeignKey(
        "iam.Device",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="media_access_logs",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "media_access_logs"
        indexes = [
            models.Index(fields=["media", "-created_at"], name="media_log_media_at_idx"),
            models.Index(fields=["user", "-created_at"], name="media_log_user_at_idx"),
            models.Index(fields=["action", "-created_at"], name="media_log_action_at_idx"),
        ]


class StorageUsage(models.Model):
    """Quota agrégé par user et type de stockage."""

    class StorageType(models.TextChoices):
        PERSONAL = "PERSONAL"
        SHARED = "SHARED"
        DOCUMENT = "DOCUMENT"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="storage_usage",
    )
    storage_type = models.CharField(max_length=20, choices=StorageType.choices)
    used_bytes = models.BigIntegerField(default=0)
    quota_bytes = models.BigIntegerField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "storage_usage"
        unique_together = [("user", "storage_type")]
