"""Routes /api/v1/media/."""

from django.urls import path

from apps.media.views.files import MediaFileView

urlpatterns = [
    path("files/<uuid:pk>", MediaFileView.as_view(), name="media-file"),
]
