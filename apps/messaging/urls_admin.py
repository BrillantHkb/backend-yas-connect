"""MESSAGERIE-F : /api/v1/admin/reported-messages."""

from django.urls import path

from apps.messaging.views.reports import AdminReportedMessageDetailView, AdminReportedMessagesView

urlpatterns = [
    path(
        "reported-messages",
        AdminReportedMessagesView.as_view(),
        name="messaging-admin-reported-messages",
    ),
    path(
        "reported-messages/<uuid:pk>",
        AdminReportedMessageDetailView.as_view(),
        name="messaging-admin-reported-message-detail",
    ),
]
