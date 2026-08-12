from urllib.parse import parse_qs

from channels.auth import AuthMiddlewareStack
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.tokens import AccessToken

from accounts.models import User
from config.db_sync import database_sync_to_async


@database_sync_to_async
def _get_user_for_token(token):
    try:
        access_token = AccessToken(token)
        return User.objects.get(pk=access_token["user_id"])
    except Exception:
        return AnonymousUser()


class JWTQueryTokenAuthMiddleware:
    """Authenticate WebSocket connections from a JWT in the query string.

    Browsers cannot set headers on WebSocket upgrades, so the access token is
    sent as ``?token=<access>``. A valid token populates ``scope["user"]``;
    a missing or invalid token leaves it anonymous (consumers close).
    """

    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        query = parse_qs(scope.get("query_string", b"").decode())
        token = query.get("token", [None])[0]
        scope["user"] = await _get_user_for_token(token) if token else AnonymousUser()
        return await self.inner(scope, receive, send)


def jwt_auth_stack(inner):
    return AuthMiddlewareStack(JWTQueryTokenAuthMiddleware(inner))
