from decimal import Decimal

from channels.testing import WebsocketCommunicator
from django.contrib.gis.geos import Point
from django.urls import reverse
from rest_framework import status

from accounts.models import User
from config.routing import application
from config.tests_base import WebsocketTestCase
from restaurants.models import MenuItem, Restaurant


def creds(role, username=None):
    return {
        "email": f"{role}@test.com",
        "username": username or role,
        "password": "testpass123",
        "role": role,
        "phone": "+1000000000",
    }


class NotificationWSTests(WebsocketTestCase):
    def setUp(self):
        self.customer = User.objects.create_user(**creds(User.Role.CUSTOMER, "cust"))
        self.vendor = User.objects.create_user(**creds(User.Role.VENDOR, "vendor"))
        self.driver = User.objects.create_user(**creds(User.Role.DRIVER, "driver1"))

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

    def test_vendor_receives_notification_bell_push(self):
        async def scenario():
            comm = self.communicator("/ws/notifications/", self.vendor)
            connected, _ = await comm.connect()
            self.assertTrue(connected)

            self.api_client.force_authenticate(self.customer)
            await self.http(
                "post",
                reverse("cart_item-list"),
                {"menu_item": self.item.id, "quantity": 1},
                format="json",
            )
            res = await self.http(
                "post",
                reverse("checkout"),
                {
                    "restaurant": self.restaurant.id,
                    "delivery_address": "456 Customer Ave",
                    "delivery_location": {"lat": 40.7130, "lng": -74.0070},
                },
                format="json",
            )
            self.assertEqual(res.status_code, status.HTTP_201_CREATED)

            payload = await comm.receive_json_from()
            self.assertEqual(payload["type"], "notification.created")
            self.assertEqual(payload["notification"]["title"], "New order")
            self.assertEqual(payload["notification"]["order_id"], res.data["id"])

            await comm.disconnect()

        self.run_async(scenario())

    def test_other_user_does_not_receive_private_notification(self):
        async def scenario():
            vendor_comm = self.communicator("/ws/notifications/", self.vendor)
            driver_comm = self.communicator("/ws/notifications/", self.driver)
            await vendor_comm.connect()
            await driver_comm.connect()

            self.api_client.force_authenticate(self.customer)
            await self.http(
                "post",
                reverse("cart_item-list"),
                {"menu_item": self.item.id, "quantity": 1},
                format="json",
            )
            await self.http(
                "post",
                reverse("checkout"),
                {
                    "restaurant": self.restaurant.id,
                    "delivery_address": "456 Customer Ave",
                    "delivery_location": {"lat": 40.7130, "lng": -74.0070},
                },
                format="json",
            )

            payload = await vendor_comm.receive_json_from()
            self.assertEqual(payload["type"], "notification.created")
            nothing = await driver_comm.receive_nothing()
            self.assertTrue(nothing)

            await vendor_comm.disconnect()
            await driver_comm.disconnect()

        self.run_async(scenario())

    def test_unauthenticated_rejected(self):
        async def scenario():
            comm = WebsocketCommunicator(application, "/ws/notifications/")
            connected, _ = await comm.connect()
            self.assertFalse(connected)

        self.run_async(scenario())
