from rest_framework.test import APITestCase

from config.celery import app as celery_app


class EagerCeleryTestCase(APITestCase):
    """APITestCase that runs Celery tasks synchronously (no broker/result store)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        celery_app.conf.task_always_eager = True
