from decimal import Decimal

from django.contrib.gis.geos import Point
from django.urls import reverse
from rest_framework import status

from accounts.models import User
from config.tests_base import EagerCeleryTestCase
from orders.models import Order
from restaurants.models import MenuItem, Restaurant

from .models import Notification


def creds(role, username=None):
    return {
        "email": f"{role}@test.com",
        "username": username or role,
        "password": "testpass123",
        "role": role,
        "phone": "+1000000000",
    }


class NotificationTests(EagerCeleryTestCase):
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

    def _checkout(self):
        self.client.force_authenticate(self.customer)
        self.client.post(
            reverse("cart_item-list"),
            {"menu_item": self.item.id, "quantity": 1},
            format="json",
        )
        return self.client.post(
            reverse("checkout"),
            {
                "restaurant": self.restaurant.id,
                "delivery_address": "456 Customer Ave",
                "delivery_location": {"lat": 40.7130, "lng": -74.0070},
            },
            format="json",
        )

    def _set_status(self, status_value):
        self.client.force_authenticate(self.vendor)
        return self.client.post(
            reverse("vendor-order-status", args=[self.order.id]),
            {"status": status_value},
            format="json",
        )

    def _make_ready(self):
        for step in (
            Order.Status.ACCEPTED,
            Order.Status.PREPARING,
            Order.Status.READY,
        ):
            res = self._set_status(step)
            self.assertEqual(res.status_code, status.HTTP_200_OK)
            self.order.refresh_from_db()

    def test_checkout_notifies_vendor(self):
        res = self._checkout()
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        notifications = Notification.objects.filter(user=self.vendor)
        self.assertEqual(notifications.count(), 1)
        self.assertEqual(notifications.first().type, Notification.Type.ORDER)
        self.assertEqual(notifications.first().order_id, res.data["id"])

    def test_vendor_status_updates_notify_customer(self):
        self._checkout()
        self.order = Order.objects.get()
        self._set_status(Order.Status.ACCEPTED)
        self._set_status(Order.Status.PREPARING)

        customer_msgs = set(
            Notification.objects.filter(user=self.customer).values_list(
                "title", flat=True
            )
        )
        self.assertEqual(
            customer_msgs, {"Order accepted", "Order being prepared"}
        )

    def test_ready_and_claim_notify_driver(self):
        self._checkout()
        self.order = Order.objects.get()
        self._make_ready()
        self.assertEqual(
            Notification.objects.filter(user=self.driver).count(), 0
        )

        self.client.force_authenticate(self.driver)
        self.client.post(reverse("driver-order-claim", args=[self.order.id]))

        for username in ("cust", "vendor"):
            self.assertTrue(
                Notification.objects.filter(
                    user__username=username, title="Driver assigned"
                ).exists()
            )

    def test_pickup_and_delivery_notify_customer_and_vendor(self):
        self._checkout()
        self.order = Order.objects.get()
        self._make_ready()

        self.client.force_authenticate(self.driver)
        self.client.post(reverse("driver-order-claim", args=[self.order.id]))
        self.client.post(reverse("driver-order-picked-up", args=[self.order.id]))
        self.client.post(reverse("driver-order-delivered", args=[self.order.id]))

        customer_titles = set(
            Notification.objects.filter(user=self.customer).values_list(
                "title", flat=True
            )
        )
        vendor_titles = set(
            Notification.objects.filter(user=self.vendor).values_list(
                "title", flat=True
            )
        )
        self.assertIn("Order on the way", customer_titles)
        self.assertIn("Order delivered", customer_titles)
        self.assertIn("Order picked up", vendor_titles)
        self.assertIn("Order delivered", vendor_titles)

    def test_cancel_notifies_vendor(self):
        self._checkout()
        self.order = Order.objects.get()
        self.client.force_authenticate(self.customer)
        res = self.client.post(reverse("order-cancel", args=[self.order.id]))
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        self.assertTrue(
            Notification.objects.filter(
                user=self.vendor, title="Order cancelled"
            ).exists()
        )

    def test_list_only_mine(self):
        self._checkout()
        for user, expected in ((self.customer, 0), (self.vendor, 1), (self.other, 0)):
            self.client.force_authenticate(user)
            res = self.client.get(reverse("notifications-list"))
            self.assertEqual(res.status_code, status.HTTP_200_OK)
            self.assertEqual(len(res.data), expected)

    def test_mark_read_and_unread_count(self):
        self._checkout()
        self.client.force_authenticate(self.vendor)
        res = self.client.get(reverse("notifications-unread-count"))
        self.assertEqual(res.data["unread_count"], 1)

        res = self.client.post(
            reverse("notification-read", args=[Notification.objects.get().id])
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data["is_read"])

        res = self.client.get(reverse("notifications-unread-count"))
        self.assertEqual(res.data["unread_count"], 0)

    def test_read_all(self):
        self._checkout()
        self.order = Order.objects.get()
        self._set_status(Order.Status.ACCEPTED)
        self._set_status(Order.Status.PREPARING)

        self.client.force_authenticate(self.vendor)
        res = self.client.post(reverse("notifications-read-all"))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["updated"], 1)
        self.assertEqual(
            Notification.objects.filter(user=self.vendor, is_read=False).count(), 0
        )
