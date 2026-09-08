"""Routes AUTH-A, montées sous /api/v1/auth/ dans config/urls.py."""

from django.urls import path

from apps.iam.views import LoginView, RefreshView

urlpatterns = [
    path("login", LoginView.as_view(), name="login"),  # POST /api/v1/auth/login
    path("refresh", RefreshView.as_view(), name="refresh"),  # POST /api/v1/auth/refresh
]
