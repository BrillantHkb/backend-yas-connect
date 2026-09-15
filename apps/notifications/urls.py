"""NOTIF-A : /api/v1/notifications + /api/v1/notification-preferences."""

from django.urls import path

from apps.notifications.views.inbox import (
    NotificationListView,
    NotificationReadView,
    ReadAllView,
    UnreadCountView,
)
from apps.notifications.views.preferences import NotificationPreferencesView

urlpatterns = [
    path(
        "notifications/unread-count",
        UnreadCountView.as_view(),
        name="notifications-unread-count",
    ),
    path("notifications/read-all", ReadAllView.as_view(), name="notifications-read-all"),
    path("notifications/<uuid:pk>/read", NotificationReadView.as_view(), name="notifications-read"),
    path("notifications", NotificationListView.as_view(), name="notifications-list"),
    path(
        "notification-preferences",
        NotificationPreferencesView.as_view(),
        name="notification-preferences",
    ),
]
