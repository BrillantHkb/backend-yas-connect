"""
Coller dans apps/calls/models.py.

Source : catalogues/APPELS-catalogue-tables.md
Phase 5 : 9 tables migrées (webrtc_sessions hors incrément MVP — voir catalogue §4).
Dépend de iam (users, devices) et media (media_files).
Messagerie : messages.call_id référence calls.id sans FK inverse.
"""

import uuid

from django.conf import settings
from django.contrib.postgres.indexes import GinIndex
from django.db import models


class Call(models.Model):
    """Appel ou réunion audio/vidéo."""

    class CallType(models.TextChoices):
        AUDIO = "AUDIO"
        VIDEO = "VIDEO"
        CONFERENCE = "CONFERENCE"
        CRISIS_ROOM = "CRISIS_ROOM"
        MEETING = "MEETING"

    class Status(models.TextChoices):
        CREATED = "CREATED"
        RINGING = "RINGING"
        ACTIVE = "ACTIVE"
        ENDED = "ENDED"
        FAILED = "FAILED"
        CANCELLED = "CANCELLED"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    caller = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="initiated_calls",
    )
    call_type = models.CharField(max_length=16, choices=CallType.choices)
    room_id = models.CharField(max_length=255, unique=True)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.CREATED
    )
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.IntegerField(default=0)
    max_participants = models.SmallIntegerField(default=2)
    is_recorded = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "calls"
        indexes = [
            models.Index(fields=["caller", "-created_at"], name="calls_caller_created_idx"),
            models.Index(fields=["status"], name="calls_status_idx"),
            models.Index(fields=["-created_at"], name="calls_created_desc_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(duration_seconds__gte=0),
                name="calls_duration_nonneg",
            ),
        ]


class CallParticipant(models.Model):
    """Participation métier d'un utilisateur à un appel."""

    class Role(models.TextChoices):
        HOST = "HOST"
        MODERATOR = "MODERATOR"
        PARTICIPANT = "PARTICIPANT"
        GUEST = "GUEST"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    call = models.ForeignKey(Call, on_delete=models.CASCADE, related_name="participants")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="call_participations",
    )
    joined_at = models.DateTimeField()
    left_at = models.DateTimeField(null=True, blank=True)
    role = models.CharField(max_length=16, choices=Role.choices)
    muted = models.BooleanField(default=False)
    camera_enabled = models.BooleanField(default=False)

    class Meta:
        db_table = "call_participants"
        unique_together = [("call", "user")]
        indexes = [
            models.Index(fields=["call", "joined_at"], name="call_part_call_joined_idx"),
        ]


class CallSession(models.Model):
    """Connexion technique (device, réseau) — plusieurs par user et par appel."""

    class NetworkType(models.TextChoices):
        WIFI = "WIFI"
        MOBILE_3G = "MOBILE_3G"
        MOBILE_4G = "MOBILE_4G"
        MOBILE_5G = "MOBILE_5G"
        ETHERNET = "ETHERNET"
        OTHER = "OTHER"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    call = models.ForeignKey(Call, on_delete=models.CASCADE, related_name="sessions")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="call_sessions",
    )
    device = models.ForeignKey(
        "iam.Device",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="call_sessions",
    )
    connection_id = models.CharField(max_length=255, blank=True, default="")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    network_type = models.CharField(
        max_length=16, choices=NetworkType.choices, default=NetworkType.OTHER
    )
    connected_at = models.DateTimeField()
    disconnected_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "call_sessions"
        indexes = [
            models.Index(fields=["call", "user"], name="call_sess_call_user_idx"),
            models.Index(fields=["device", "-connected_at"], name="call_sess_device_conn_idx"),
        ]


class LiveKitRoom(models.Model):
    """Salle LiveKit — une par appel."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    call = models.OneToOneField(
        Call, on_delete=models.CASCADE, related_name="livekit_room"
    )
    room_name = models.CharField(max_length=255, unique=True)
    livekit_sid = models.CharField(max_length=255, blank=True, default="")
    max_participants = models.SmallIntegerField(default=2)
    created_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "livekit_rooms"


class MediaTrack(models.Model):
    """Piste média live publiée dans un appel."""

    class TrackType(models.TextChoices):
        AUDIO = "AUDIO"
        VIDEO = "VIDEO"
        SCREEN_SHARE = "SCREEN_SHARE"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    call = models.ForeignKey(Call, on_delete=models.CASCADE, related_name="media_tracks")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="published_call_tracks",
    )
    track_type = models.CharField(max_length=16, choices=TrackType.choices)
    codec = models.CharField(max_length=50, blank=True, default="")
    bitrate = models.IntegerField(default=0)
    resolution = models.CharField(max_length=30, blank=True, default="")
    active = models.BooleanField(default=True)

    class Meta:
        db_table = "media_tracks"
        indexes = [
            models.Index(fields=["call", "active"], name="media_tracks_call_active_idx"),
        ]


class Recording(models.Model):
    """Enregistrement d'appel stocké dans Médias."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    call = models.ForeignKey(Call, on_delete=models.CASCADE, related_name="recordings")
    media = models.ForeignKey(
        "media.MediaFile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="call_recordings",
    )
    duration_seconds = models.IntegerField(default=0)
    format = models.CharField(max_length=30, blank=True, default="")
    encrypted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "recordings"
        indexes = [
            models.Index(fields=["call", "-created_at"], name="recordings_call_created_idx"),
        ]


class ScreenShare(models.Model):
    """Épisode de partage d'écran pendant un appel."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    call = models.ForeignKey(Call, on_delete=models.CASCADE, related_name="screen_shares")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="screen_shares",
    )
    started_at = models.DateTimeField()
    ended_at = models.DateTimeField(null=True, blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        db_table = "screen_shares"
        indexes = [
            models.Index(fields=["call", "-started_at"], name="screen_share_call_start_idx"),
        ]


class CallQualityMetric(models.Model):
    """Échantillon QoS — INSERT only ; rétention 90 j en MVP."""

    id = models.BigAutoField(primary_key=True)
    call = models.ForeignKey(
        Call, on_delete=models.CASCADE, related_name="quality_metrics"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="call_quality_metrics",
    )
    latency_ms = models.IntegerField(null=True, blank=True)
    jitter_ms = models.IntegerField(null=True, blank=True)
    packet_loss = models.DecimalField(
        max_digits=6, decimal_places=3, null=True, blank=True
    )
    bitrate = models.IntegerField(null=True, blank=True)
    fps = models.IntegerField(null=True, blank=True)
    cpu_usage = models.IntegerField(null=True, blank=True)
    network_type = models.CharField(max_length=20, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "call_quality_metrics"
        indexes = [
            models.Index(
                fields=["call", "-created_at"],
                name="call_qos_call_created_idx",
            ),
            models.Index(
                fields=["user", "-created_at"],
                name="call_qos_user_created_idx",
            ),
            models.Index(fields=["created_at"], name="call_qos_created_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(packet_loss__isnull=True)
                | (models.Q(packet_loss__gte=0) & models.Q(packet_loss__lte=100)),
                name="call_qos_packet_loss_range",
            ),
        ]


class MeetingHistory(models.Model):
    """Compte-rendu post-appel (transcript, résumé IA)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    call = models.OneToOneField(
        Call, on_delete=models.CASCADE, related_name="meeting_history"
    )
    title = models.CharField(max_length=255, blank=True, default="")
    summary = models.TextField(blank=True, default="")
    transcript = models.TextField(blank=True, default="")
    ai_summary = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "meeting_history"
        indexes = [
            GinIndex(
                fields=["transcript"],
                name="meeting_hist_transcript_gin",
                opclasses=["gin_trgm_ops"],
            ),
        ]
