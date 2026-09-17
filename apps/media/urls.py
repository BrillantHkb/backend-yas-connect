"""Routes /api/v1/media/."""

from django.urls import path

from apps.media.views.audio import MediaAudioTranscribeView, MediaAudioTranscriptionsView
from apps.media.views.files import MediaFileView
from apps.media.views.images import MediaImageOptimizeView, MediaImageView
from apps.media.views.uploads import (
    MediaDetailView,
    MediaDirectUploadView,
    MediaDownloadView,
    MediaUploadCompleteView,
    MediaUploadInitView,
)
from apps.media.views.videos import (
    MediaVideoStreamView,
    MediaVideoThumbnailView,
    MediaVideoTranscodeView,
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
    path("<uuid:pk>/image/optimize", MediaImageOptimizeView.as_view(), name="media-image-optimize"),
    path("<uuid:pk>/image", MediaImageView.as_view(), name="media-image"),
    path(
        "<uuid:pk>/video/transcode", MediaVideoTranscodeView.as_view(), name="media-video-transcode"
    ),
    path("<uuid:pk>/video/stream", MediaVideoStreamView.as_view(), name="media-video-stream"),
    path(
        "<uuid:pk>/video/thumbnail", MediaVideoThumbnailView.as_view(), name="media-video-thumbnail"
    ),
    path(
        "<uuid:pk>/audio/transcribe",
        MediaAudioTranscribeView.as_view(),
        name="media-audio-transcribe",
    ),
    path(
        "<uuid:pk>/audio/transcriptions",
        MediaAudioTranscriptionsView.as_view(),
        name="media-audio-transcriptions",
    ),
    path("<uuid:pk>", MediaDetailView.as_view(), name="media-detail"),
]
