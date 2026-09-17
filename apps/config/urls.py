"""Routes /api/v1/config."""

from django.urls import path

from apps.config.views import PublicConfigView

urlpatterns = [
    path("config", PublicConfigView.as_view(), name="public-config"),
]
