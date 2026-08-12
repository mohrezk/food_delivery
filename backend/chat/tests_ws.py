from decimal import Decimal

from channels.testing import WebsocketCommunicator
from django.contrib.gis.geos import Point
from django.urls import reverse
from rest_framework import status

from accounts.models import User
from config.db_sync import database_sync_to_async
from config.routing import application
from config.tests_base import WebsocketTestCase
from orders.models import Order
from restaurants.models import MenuItem, Restaurant

from .models import Conversation


def creds(role, username=None):
    return {
        "email": f"{role}@test.com",
        "username": username or role,
        "password": "testpass123",
        "role": role,
        "phone": "+1000000000",
    }


class ChatWSTests(WebsocketTestCase):
    def setUp(self):
        self.customer = User.objects.create_user(**creds(User.Role.CUSTOMER, "cust"))
        self.vendor = User.objects.create_user(**creds(User.Role.VENDOR, "vendor"))
        self.driver = User.objects.create_user(**creds(User.Role.DRIVER, "driver1"))
        self.other = User.objects.create_user(**creds(User.Role.CUSTOMER, "other"))

        self.restaurant = Restaurant.objects.create(
            owner=self.vendor,
            name="Burger House",
            address="123 Grill St",
            location=Point(-74.0060, 40.7128, srid=4326),
            status=Restaurant.Status.OPEN,
        )
        self.item = MenuItem.objects.create(
            restaurant=self.restaurant,
            name="Classic Burger",
            description="Beef patty",
            price=Decimal("8.99"),
        )
        self.order = Order.objects.create(
            user=self.customer,
            restaurant=self.restaurant,
            status=Order.Status.READY,
            total_price=Decimal("8.99"),
            delivery_address="456 Customer Ave",
            delivery_location=Point(-74.0070, 40.7130, srid=4326),
        )

        self.api_client.force_authenticate(self.driver)
        res = self.api_client.post(reverse("driver-order-claim", args=[self.order.id]))
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_participants_receive_realtime_message(self):
        async def scenario():
            conv = await database_sync_to_async(Conversation.objects.get)()
            customer_comm = self.communicator(f"/ws/chat/{conv.id}/", self.customer)
            vendor_comm = self.communicator(f"/ws/chat/{conv.id}/", self.vendor)
            c_ok, _ = await customer_comm.connect()
            v_ok, _ = await vendor_comm.connect()
            self.assertTrue(c_ok)
            self.assertTrue(v_ok)

            self.api_client.force_authenticate(self.customer)
            res = await self.http(
                "post",
                reverse("chat-send-message", args=[conv.id]),
                {"body": "Hi, is my order almost ready?"},
                format="json",
            )
            self.assertEqual(res.status_code, status.HTTP_201_CREATED)

            c_payload = await customer_comm.receive_json_from()
            v_payload = await vendor_comm.receive_json_from()
            self.assertEqual(c_payload["type"], "message.created")
            self.assertEqual(v_payload["type"], "message.created")
            self.assertEqual(c_payload["message"]["body"], "Hi, is my order almost ready?")
            self.assertEqual(v_payload["message"]["body"], "Hi, is my order almost ready?")

            await customer_comm.disconnect()
            await vendor_comm.disconnect()

        self.run_async(scenario())

    def test_non_participant_rejected(self):
        async def scenario():
            conv = await database_sync_to_async(Conversation.objects.get)()
            comm = self.communicator(f"/ws/chat/{conv.id}/", self.other)
            connected, _ = await comm.connect()
            self.assertFalse(connected)

        self.run_async(scenario())

    def test_invalid_token_rejected(self):
        async def scenario():
            conv = await database_sync_to_async(Conversation.objects.get)()
            comm = WebsocketCommunicator(
                application, f"/ws/chat/{conv.id}/?token=not-a-valid-jwt"
            )
            connected, _ = await comm.connect()
            self.assertFalse(connected)

        self.run_async(scenario())
