from decimal import Decimal

from channels.testing import WebsocketCommunicator
from django.contrib.gis.geos import Point
from django.urls import reverse
from rest_framework import status

from accounts.models import User
from config.routing import application
from config.tests_base import WebsocketTestCase
from orders.models import Order
from restaurants.models import MenuItem, Restaurant


def creds(role, username=None):
    return {
        "email": f"{role}@test.com",
        "username": username or role,
        "password": "testpass123",
        "role": role,
        "phone": "+1000000000",
    }


class OrderTrackingWSTests(WebsocketTestCase):
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

    def test_customer_receives_status_change(self):
        async def scenario():
            self.api_client.force_authenticate(self.driver)
            res = await self.http(
                "post", reverse("driver-order-claim", args=[self.order.id])
            )
            self.assertEqual(res.status_code, status.HTTP_200_OK)

            comm = self.communicator(f"/ws/orders/{self.order.id}/", self.customer)
            connected, _ = await comm.connect()
            self.assertTrue(connected)

            self.api_client.force_authenticate(self.driver)
            res = await self.http(
                "post", reverse("driver-order-picked-up", args=[self.order.id])
            )
            self.assertEqual(res.status_code, status.HTTP_200_OK)

            payload = await comm.receive_json_from()
            self.assertEqual(payload["type"], "order.status")
            self.assertEqual(payload["order"]["id"], self.order.id)
            self.assertEqual(payload["order"]["status"], "PICKED_UP")

            await comm.disconnect()

        self.run_async(scenario())

    def test_customer_receives_driver_location(self):
        async def scenario():
            # assign the driver first (order is READY, no driver yet)
            self.api_client.force_authenticate(self.driver)
            res = await self.http(
                "post", reverse("driver-order-claim", args=[self.order.id])
            )
            self.assertEqual(res.status_code, status.HTTP_200_OK)

            comm = self.communicator(f"/ws/orders/{self.order.id}/", self.customer)
            connected, _ = await comm.connect()
            self.assertTrue(connected)

            self.api_client.force_authenticate(self.driver)
            res = await self.http(
                "patch",
                reverse("driver-location"),
                {"location": {"lat": 40.7140, "lng": -74.0080}},
                format="json",
            )
            self.assertEqual(res.status_code, status.HTTP_200_OK)

            payload = await comm.receive_json_from()
            self.assertEqual(payload["type"], "order.location")
            self.assertEqual(payload["order_id"], self.order.id)
            self.assertEqual(payload["location"]["lat"], 40.7140)
            self.assertEqual(payload["location"]["lng"], -74.0080)

            await comm.disconnect()

        self.run_async(scenario())

    def test_non_participant_rejected(self):
        async def scenario():
            comm = self.communicator(f"/ws/orders/{self.order.id}/", self.other)
            connected, _ = await comm.connect()
            self.assertFalse(connected)

        self.run_async(scenario())


class VendorAlertWSTests(WebsocketTestCase):
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

    def test_vendor_receives_new_order_alert(self):
        async def scenario():
            comm = self.communicator("/ws/vendor/orders/", self.vendor)
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
            self.assertEqual(payload["type"], "order.new")
            self.assertEqual(payload["order"]["id"], res.data["id"])

            await comm.disconnect()

        self.run_async(scenario())

    def test_non_vendor_rejected(self):
        async def scenario():
            comm = self.communicator("/ws/vendor/orders/", self.customer)
            connected, _ = await comm.connect()
            self.assertFalse(connected)

        self.run_async(scenario())

    def test_invalid_token_rejected(self):
        async def scenario():
            comm = WebsocketCommunicator(
                application, "/ws/vendor/orders/?token=not-a-valid-jwt"
            )
            connected, _ = await comm.connect()
            self.assertFalse(connected)

        self.run_async(scenario())
