"""
ASGI config — HTTP (Django) + WebSocket (Channels) under /ws/.
"""

import os
import sys

from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from django.core.asgi import get_asgi_application

from realtime.middleware import JWTAuthMiddlewareStack

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

django_asgi_app = get_asgi_application()

import realtime.routing  # noqa: E402

if "pytest" not in sys.modules:
    from core.signals import register_shutdown_handlers

    register_shutdown_handlers()

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": AllowedHostsOriginValidator(
            JWTAuthMiddlewareStack(URLRouter(realtime.routing.websocket_urlpatterns)),
        ),
    },
)
