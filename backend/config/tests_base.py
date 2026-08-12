import asyncio

from django.db import connections
from django.test import TransactionTestCase, override_settings
from rest_framework.test import APIClient, APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from config.celery import app as celery_app
from config.db_sync import ClosingSyncToAsync

_IN_MEMORY_CHANNEL_LAYER = {
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
}


class EagerCeleryTestCase(APITestCase):
    """APITestCase that runs Celery tasks synchronously (no broker/result store)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        celery_app.conf.task_always_eager = True


class WebsocketTestCase(TransactionTestCase):
    """Base for WebSocket tests.

    Why TransactionTestCase? Channel consumers hit the DB on worker threads;
    a transactional TestCase would both hide uncommitted test data from those
    threads and leak their connections between tests. TransactionTestCase
    commits data, and tearDown closes every connection to prevent leaks.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        celery_app.conf.task_always_eager = True
        cls._channel_override = override_settings(
            CHANNEL_LAYERS=_IN_MEMORY_CHANNEL_LAYER
        )
        cls._channel_override.enable()

    @classmethod
    def tearDownClass(cls):
        cls._channel_override.disable()
        super().tearDownClass()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._api_client = None

    @property
    def api_client(self):
        if self._api_client is None:
            self._api_client = APIClient()
        return self._api_client

    def tearDown(self):
        connections.close_all()
        super().tearDown()

    def communicator(self, path, user):
        from channels.testing import WebsocketCommunicator

        from config.routing import application

        token = RefreshToken.for_user(user).access_token
        sep = "&" if "?" in path else "?"
        return WebsocketCommunicator(application, f"{path}{sep}token={token}")

    def run_async(self, coro):
        return asyncio.run(coro)

    def http(self, method, *args, **kwargs):
        """Run a synchronous API call, closing worker-thread DB connections."""
        return ClosingSyncToAsync(getattr(self.api_client, method))(*args, **kwargs)
