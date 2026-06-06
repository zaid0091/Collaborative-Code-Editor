"""
ASGI config — HTTP (Django) + WebSocket (Channels) under /ws/.
"""

import asyncio
import os
import signal
import socket
import sys

from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from django.core.asgi import get_asgi_application

from realtime.middleware import JWTAuthMiddlewareStack

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

django_asgi_app = get_asgi_application()

import realtime.routing  # noqa: E402


def handle_sigterm(*args):
    from apps.collaboration.lifecycle import flush_active_buffers_on_shutdown

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(flush_active_buffers_on_shutdown(socket.gethostname()))
    except RuntimeError:
        asyncio.run(flush_active_buffers_on_shutdown(socket.gethostname()))


if "pytest" not in sys.modules:
    signal.signal(signal.SIGTERM, handle_sigterm)

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": AllowedHostsOriginValidator(
            JWTAuthMiddlewareStack(URLRouter(realtime.routing.websocket_urlpatterns)),
        ),
    },
)
