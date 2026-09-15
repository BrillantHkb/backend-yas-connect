"""Routes GET /api/v1/users (picker) + /{id}. path("") avant path("<uuid:pk>")."""

from django.urls import path

from apps.iam.views.users import UserPublicView, UserSearchView

urlpatterns = [
    path("", UserSearchView.as_view(), name="user-search"),
    path("<uuid:pk>", UserPublicView.as_view(), name="user-public"),
]
