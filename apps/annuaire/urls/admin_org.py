"""ANNUAIRE-B : /api/v1/admin/segment-types|segments(/tree). Monté en plus d’AUTH-R/ADMIN-A."""

from django.urls import path

from apps.annuaire.views.admin_org import (
    AdminSegmentDetailView,
    AdminSegmentListCreateView,
    AdminSegmentTreeView,
    AdminSegmentTypeDetailView,
    AdminSegmentTypeListCreateView,
)

urlpatterns = [
    path("segment-types", AdminSegmentTypeListCreateView.as_view(), name="admin-segment-types"),
    path(
        "segment-types/<uuid:pk>",
        AdminSegmentTypeDetailView.as_view(),
        name="admin-segment-types-detail",
    ),
    path("segments/tree", AdminSegmentTreeView.as_view(), name="admin-segments-tree"),  # avant {id}
    path("segments", AdminSegmentListCreateView.as_view(), name="admin-segments"),
    path("segments/<uuid:pk>", AdminSegmentDetailView.as_view(), name="admin-segments-detail"),
]
