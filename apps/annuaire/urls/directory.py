"""Dropdowns publics inscription : /api/v1/directory/regions|segment-types|segments."""

from django.urls import path

from apps.annuaire.views.directory import (
    DirectoryRegionsView,
    DirectorySegmentsView,
    DirectorySegmentTypesView,
)

urlpatterns = [
    path("regions", DirectoryRegionsView.as_view(), name="directory-regions"),
    path("segment-types", DirectorySegmentTypesView.as_view(), name="directory-segment-types"),
    path("segments", DirectorySegmentsView.as_view(), name="directory-segments"),
]
