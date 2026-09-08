"""
Source : catalogues/CONFIG-catalogue-tables.md
AUTH-B : URI LDAP + job sync (départs, disable AD, expiration).
"""

import uuid

from django.conf import settings
from django.contrib.postgres.indexes import GinIndex
from django.db import models


class SystemSetting(models.Model):
    """Paramètre runtime (URI LDAP, secrets bind AUTH-B). Secrets : is_sensitive."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    category = models.CharField(max_length=64, db_index=True)
    setting_key = models.CharField(max_length=128)
    setting_value = models.JSONField()
    value_type = models.CharField(max_length=32, default="string")
    is_sensitive = models.BooleanField(default=False)  # jamais exposé en API
    editable = models.BooleanField(default=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_system_settings",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "system_settings"
        unique_together = [("category", "setting_key")]
        indexes = [
            GinIndex(fields=["setting_value"], name="sys_settings_value_gin"),
        ]

    def __str__(self):
        return f"{self.category}.{self.setting_key}"


class ScheduledJob(models.Model):
    """Planification (AUTH-16 ldap_sync_users). Exécuté par run_scheduled_jobs."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    job_name = models.CharField(max_length=128, unique=True)
    module = models.CharField(max_length=64)
    cron_expression = models.CharField(max_length=64, null=True, blank=True)
    interval_seconds = models.IntegerField(null=True, blank=True)
    handler = models.CharField(max_length=255)
    enabled = models.BooleanField(default=True)
    last_execution = models.DateTimeField(null=True, blank=True)
    next_execution = models.DateTimeField(null=True, blank=True, db_index=True)
    last_status = models.CharField(max_length=32, null=True, blank=True)
    last_error = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "scheduled_jobs"
        indexes = [
            models.Index(fields=["enabled", "next_execution"], name="sched_jobs_due_idx"),
        ]

    def __str__(self):
        return self.job_name


class FeatureFlag(models.Model):
    """Rollout optionnel. 0 ligne obligatoire AUTH-B."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    feature_code = models.CharField(max_length=64, unique=True)
    feature_name = models.CharField(max_length=128)
    enabled = models.BooleanField(default=False)
    rollout_percentage = models.SmallIntegerField(default=100)
    target_roles = models.JSONField(default=list, blank=True)
    target_platforms = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "feature_flags"
        indexes = [
            GinIndex(fields=["target_roles"], name="ff_target_roles_gin"),
        ]

    def __str__(self):
        return self.feature_code
