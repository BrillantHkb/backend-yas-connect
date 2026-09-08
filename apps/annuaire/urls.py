"""Dropdowns publics inscription : /api/v1/directory/regions|segments."""

from django.urls import path

from apps.annuaire.views import DirectoryRegionsView, DirectorySegmentsView

urlpatterns = [
    path("regions", DirectoryRegionsView.as_view(), name="directory-regions"),
    path("segments", DirectorySegmentsView.as_view(), name="directory-segments"),
]
