from django.urls import path

from apps.realtime.consumers import PresenceConsumer

websocket_urlpatterns = [
    path("ws/v1/presence", PresenceConsumer.as_asgi()),
]
