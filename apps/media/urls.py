"""Routes /api/v1/media/."""

from django.urls import path

from apps.media.views.files import MediaFileView
from apps.media.views.uploads import (
    MediaDetailView,
    MediaDirectUploadView,
    MediaDownloadView,
    MediaUploadCompleteView,
    MediaUploadInitView,
)

urlpatterns = [
    path("files/<uuid:pk>", MediaFileView.as_view(), name="media-file"),
    path("uploads", MediaUploadInitView.as_view(), name="media-uploads-init"),
    path(
        "uploads/<uuid:upload_id>/complete",
        MediaUploadCompleteView.as_view(),
        name="media-uploads-complete",
    ),
    path("upload", MediaDirectUploadView.as_view(), name="media-upload-direct"),
    path("<uuid:pk>/download", MediaDownloadView.as_view(), name="media-download"),
    path("<uuid:pk>", MediaDetailView.as_view(), name="media-detail"),
]
