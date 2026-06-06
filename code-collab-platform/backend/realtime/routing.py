"""WebSocket URL routing."""

from django.urls import re_path

from apps.collaboration.consumers import CollaborationConsumer

websocket_urlpatterns = [
    re_path(
        r"^ws/collab/(?P<file_id>[0-9a-f-]{36})/$",
        CollaborationConsumer.as_asgi(),
    ),
]
