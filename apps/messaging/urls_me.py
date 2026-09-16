"""MESSAGERIE-F/E : /api/v1/me/blocked-users, /api/v1/me/message-bookmarks."""

from django.urls import path

from apps.messaging.views.blocking import BlockedUserDetailView, BlockedUsersView
from apps.messaging.views.bookmarks import MyBookmarksView

urlpatterns = [
    path("blocked-users", BlockedUsersView.as_view(), name="messaging-me-blocked-users"),
    path(
        "blocked-users/<uuid:user_id>",
        BlockedUserDetailView.as_view(),
        name="messaging-me-blocked-user-detail",
    ),
    path("message-bookmarks", MyBookmarksView.as_view(), name="messaging-me-bookmarks"),
]
