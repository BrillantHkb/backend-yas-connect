"""Routes GET /api/v1/users/{id}."""

from django.urls import path

from apps.iam.views.users import UserPublicView

urlpatterns = [
    path("<uuid:pk>", UserPublicView.as_view(), name="user-public"),
]
