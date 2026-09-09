"""Route liveness, montée à la racine (GET /health)."""

from django.urls import path

from apps.core.views.health import HealthView

urlpatterns = [
    path("health", HealthView.as_view(), name="health"),
]
