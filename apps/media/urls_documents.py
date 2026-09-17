"""MEDIA-E : /api/v1/documents (GED, ressource distincte de /api/v1/media)."""

from django.urls import path

from apps.media.views.documents import (
    DocumentDetailView,
    DocumentListCreateView,
    DocumentPreviewView,
    DocumentVersionsView,
)

urlpatterns = [
    path("documents", DocumentListCreateView.as_view(), name="documents-list-create"),
    path("documents/<uuid:pk>", DocumentDetailView.as_view(), name="documents-detail"),
    path("documents/<uuid:pk>/versions", DocumentVersionsView.as_view(), name="documents-versions"),
    path("documents/<uuid:pk>/preview", DocumentPreviewView.as_view(), name="documents-preview"),
]
