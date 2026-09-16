"""MESSAGERIE-A/B : /api/v1/conversations, /api/v1/messages."""

from django.urls import path

from apps.messaging.views.conversations import (
    ConversationArchiveView,
    ConversationByUuidView,
    ConversationDetailView,
    ConversationListCreateView,
    ConversationMuteView,
    ConversationPinnedMessagesView,
    ConversationPinView,
)
from apps.messaging.views.messages import (
    MessageDetailView,
    MessageListCreateView,
    MessageSearchView,
)

urlpatterns = [
    path("conversations", ConversationListCreateView.as_view(), name="messaging-conversations"),
    path(
        "conversations/by-uuid/<uuid:conversation_uuid>",
        ConversationByUuidView.as_view(),
        name="messaging-conversation-by-uuid",  # avant <uuid:pk> (segment littéral)
    ),
    path(
        "conversations/<uuid:pk>",
        ConversationDetailView.as_view(),
        name="messaging-conversation-detail",
    ),
    path(
        "conversations/<uuid:pk>/archive",
        ConversationArchiveView.as_view(),
        name="messaging-conversation-archive",
    ),
    path(
        "conversations/<uuid:pk>/inbox",
        ConversationPinView.as_view(),
        name="messaging-conversation-pin",
    ),
    path(
        "conversations/<uuid:pk>/settings",
        ConversationMuteView.as_view(),
        name="messaging-conversation-mute",
    ),
    path(
        "conversations/<uuid:pk>/pinned-messages",
        ConversationPinnedMessagesView.as_view(),
        name="messaging-conversation-pinned-messages",
    ),
    path(
        "conversations/<uuid:pk>/messages/search",
        MessageSearchView.as_view(),
        name="messaging-messages-search",  # avant /messages (segment littéral)
    ),
    path(
        "conversations/<uuid:pk>/messages",
        MessageListCreateView.as_view(),
        name="messaging-messages",
    ),
    path("messages/<uuid:pk>", MessageDetailView.as_view(), name="messaging-message-detail"),
]
