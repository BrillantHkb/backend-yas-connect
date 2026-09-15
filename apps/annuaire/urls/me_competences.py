"""ANNUAIRE-D : /me/skills + /me/certifications. Monté sous /api/v1/me/."""

from django.urls import path

from apps.annuaire.views.competences import (
    MeCertificationDetailView,
    MeCertificationListCreateView,
    MeSkillDetailView,
    MeSkillListCreateView,
)

urlpatterns = [
    path("skills", MeSkillListCreateView.as_view(), name="me-skills"),
    path("skills/<uuid:pk>", MeSkillDetailView.as_view(), name="me-skills-detail"),
    path("certifications", MeCertificationListCreateView.as_view(), name="me-certifications"),
    path(
        "certifications/<uuid:pk>",
        MeCertificationDetailView.as_view(),
        name="me-certifications-detail",
    ),
]
