from django.urls import path

from apps.messaging.consumers import MessagingConsumer
from apps.realtime.consumers import PresenceConsumer

websocket_urlpatterns = [
    path("ws/v1/presence", PresenceConsumer.as_asgi()),
    path("ws/v1/messaging/", MessagingConsumer.as_asgi()),
]
