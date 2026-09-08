"""
Coller dans apps/annuaire/models.py.

Source : catalogues/ANNUAIRE-catalogue-tables.md
AUTH-A : 5 tables créées. Seed ANNUAIRE-A : types + segment YAS (login n’écrit rien).
Write : ANNUAIRE-B (arbre), C (user_segments), D (skills/certifs).
users.segment_id (IAM) reste un UUID sans FK pour éviter un cycle iam ↔ annuaire.
"""

import uuid

from django.conf import settings
from django.contrib.postgres.indexes import GinIndex
from django.db import models


class SegmentType(models.Model):
    """Type d’unité org (Direction, Service, …)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=50, unique=True)  # ex. DIRECTION
    name = models.CharField(max_length=200, unique=True)  # libellé
    level = models.SmallIntegerField(default=0)  # profondeur dans l’arbre de types
    description = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "segment_types"

    def __str__(self):
        return self.code


class Segment(models.Model):
    """Unité organisationnelle. users.segment_id (IAM) = copie de l’unité courante."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=50, unique=True, db_index=True)  # ex. NOC-LOME
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)
    segment_type = models.ForeignKey(
        SegmentType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="segments",
    )
    parent_segment = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="children",
    )  # hiérarchie
    responsable = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="segments_as_responsable",
    )  # N+1 d’unité ; remplace users.manager_id
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "segments"
        indexes = [
            models.Index(fields=["parent_segment", "is_active"], name="segments_parent_active_idx"),
            GinIndex(fields=["name"], name="segments_name_trgm", opclasses=["gin_trgm_ops"]),
        ]

    def __str__(self):
        return self.code


class UserSegment(models.Model):
    """Affectation user ↔ segment (historique). Distinct de users.job_title / segment_id."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    is_active = models.BooleanField(default=True)  # affectation en cours
    start_date = models.DateTimeField()
    end_date = models.DateTimeField(null=True, blank=True)  # NULL = encore en poste
    position = models.CharField(max_length=100, blank=True, default="")  # poste dans l’unité
    position_description = models.CharField(max_length=255, blank=True, default="")
    segment = models.ForeignKey(
        Segment, on_delete=models.CASCADE, related_name="memberships"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="segment_memberships",
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_segment_memberships",
    )  # qui a affecté (RH)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "user_segments"
        indexes = [
            models.Index(fields=["user", "is_active"], name="user_seg_user_active_idx"),
            models.Index(fields=["segment", "is_active"], name="user_seg_seg_active_idx"),
        ]


class UserSkill(models.Model):
    """Compétence déclarée (recherche expert). 0 ligne AUTH-01."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    skill_name = models.CharField(max_length=150)
    level = models.SmallIntegerField(default=0)  # 1–5 (validation applicative)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="skills"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "user_skills"
        unique_together = [("user", "skill_name")]
        indexes = [
            GinIndex(fields=["skill_name"], name="user_skills_name_trgm", opclasses=["gin_trgm_ops"]),
        ]


class UserCertification(models.Model):
    """Certification. document → media_files (scan). 0 ligne AUTH-01."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    certification_name = models.CharField(max_length=150)
    issued_at = models.DateField(null=True, blank=True)
    document = models.ForeignKey(
        "media.MediaFile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="certification_documents",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="certifications",
    )

    class Meta:
        db_table = "user_certifications"
        indexes = [
            GinIndex(
                fields=["certification_name"],
                name="user_certs_name_trgm",
                opclasses=["gin_trgm_ops"],
            ),
        ]
