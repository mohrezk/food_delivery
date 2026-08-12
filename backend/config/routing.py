from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

import chat.routing
import notifications.routing
import orders.routing
from config.ws_auth import jwt_auth_stack

django_asgi_app = get_asgi_application()

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": jwt_auth_stack(
            URLRouter(
                chat.routing.websocket_urlpatterns
                + orders.routing.websocket_urlpatterns
                + notifications.routing.websocket_urlpatterns
            )
        ),
    }
)
