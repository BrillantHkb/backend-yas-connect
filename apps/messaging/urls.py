"""MESSAGERIE-A/B/C/D : /api/v1/conversations, /api/v1/messages."""

from django.urls import path

from apps.messaging.views.conversations import (
    ConversationArchiveView,
    ConversationByUuidView,
    ConversationDetailView,
    ConversationLeaveView,
    ConversationListCreateView,
    ConversationMuteView,
    ConversationPinnedMessagesView,
    ConversationPinView,
    GroupSettingsView,
    MemberDetailView,
    MemberListCreateView,
)
from apps.messaging.views.messages import (
    ConversationReadView,
    MessageDeliveredView,
    MessageDetailView,
    MessageListCreateView,
    MessageReadView,
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
        "conversations/<uuid:pk>/group-settings",
        GroupSettingsView.as_view(),
        name="messaging-conversation-group-settings",
    ),
    path(
        "conversations/<uuid:pk>/pinned-messages",
        ConversationPinnedMessagesView.as_view(),
        name="messaging-conversation-pinned-messages",
    ),
    path(
        "conversations/<uuid:pk>/members",
        MemberListCreateView.as_view(),
        name="messaging-members",
    ),
    path(
        "conversations/<uuid:pk>/members/<uuid:user_id>",
        MemberDetailView.as_view(),
        name="messaging-member-detail",
    ),
    path(
        "conversations/<uuid:pk>/leave", ConversationLeaveView.as_view(), name="messaging-leave"
    ),
    path(
        "conversations/<uuid:pk>/read",
        ConversationReadView.as_view(),
        name="messaging-conversation-read",
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
    path(
        "messages/<uuid:pk>/delivered",
        MessageDeliveredView.as_view(),
        name="messaging-message-delivered",
    ),
    path("messages/<uuid:pk>/read", MessageReadView.as_view(), name="messaging-message-read"),
]
