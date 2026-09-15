"""ANNUAIRE-C : /admin/users/{id}/segments + /admin/user-segments/{id}."""

from django.urls import path

from apps.annuaire.views.admin_assignments import (
    AdminUserSegmentDetailView,
    AdminUserSegmentListCreateView,
)

urlpatterns = [
    path(
        "users/<uuid:user_id>/segments",
        AdminUserSegmentListCreateView.as_view(),
        name="admin-user-segments",
    ),
    path(
        "user-segments/<uuid:pk>",
        AdminUserSegmentDetailView.as_view(),
        name="admin-user-segments-detail",
    ),
]
