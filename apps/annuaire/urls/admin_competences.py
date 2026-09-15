"""ANNUAIRE-D : /admin/users/{id}/skills|certifications + /admin/user-skills|user-certifications."""

from django.urls import path

from apps.annuaire.views.competences import (
    AdminUserCertificationDetailView,
    AdminUserCertificationListCreateView,
    AdminUserSkillDetailView,
    AdminUserSkillListCreateView,
)

urlpatterns = [
    path(
        "users/<uuid:user_id>/skills",
        AdminUserSkillListCreateView.as_view(),
        name="admin-user-skills",
    ),
    path(
        "user-skills/<uuid:pk>",
        AdminUserSkillDetailView.as_view(),
        name="admin-user-skills-detail",
    ),
    path(
        "users/<uuid:user_id>/certifications",
        AdminUserCertificationListCreateView.as_view(),
        name="admin-user-certifications",
    ),
    path(
        "user-certifications/<uuid:pk>",
        AdminUserCertificationDetailView.as_view(),
        name="admin-user-certifications-detail",
    ),
]
