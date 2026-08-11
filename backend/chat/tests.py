from decimal import Decimal

from django.contrib.gis.geos import Point
from django.urls import reverse
from rest_framework import status

from accounts.models import User
from config.tests_base import EagerCeleryTestCase
from notifications.models import Notification
from restaurants.models import MenuItem, Restaurant
from orders.models import Order

from .models import Conversation, Message


def creds(role, username=None):
    return {
        "email": f"{role}@test.com",
        "username": username or role,
        "password": "testpass123",
        "role": role,
        "phone": "+1000000000",
    }


class ChatTests(EagerCeleryTestCase):
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

    def _claim(self):
        self.client.force_authenticate(self.driver)
        return self.client.post(reverse("driver-order-claim", args=[self.order.id]))

    def test_conversation_auto_created_on_claim(self):
        res = self._claim()
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(Conversation.objects.count(), 1)
        conv = Conversation.objects.get()
        self.assertEqual(conv.order, self.order)
        self.assertEqual(
            set(conv.participants.values_list("username", flat=True)),
            {"cust", "vendor", "driver1"},
        )

    def test_list_only_own_conversations(self):
        self._claim()
        for user, expected in (
            (self.customer, 1),
            (self.vendor, 1),
            (self.driver, 1),
            (self.other, 0),
        ):
            self.client.force_authenticate(user)
            res = self.client.get(reverse("chat-conversations"))
            self.assertEqual(res.status_code, status.HTTP_200_OK)
            self.assertEqual(len(res.data), expected)

    def test_non_participant_gets_404(self):
        self._claim()
        conv = Conversation.objects.get()
        self.client.force_authenticate(self.other)
        res = self.client.get(reverse("chat-conversation-detail", args=[conv.id]))
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_send_message_creates_message_and_notifies_participants(self):
        self._claim()
        conv = Conversation.objects.get()
        self.client.force_authenticate(self.customer)
        res = self.client.post(
            reverse("chat-send-message", args=[conv.id]),
            {"body": "Hi, is my order almost ready?"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Message.objects.count(), 1)
        message = Message.objects.get()
        self.assertEqual(message.sender, self.customer)
        self.assertFalse(message.is_read)

        notifications = Notification.objects.filter(type=Notification.Type.CHAT)
        self.assertEqual(notifications.count(), 2)
        self.assertEqual(
            set(notifications.values_list("user__username", flat=True)),
            {"vendor", "driver1"},
        )

    def test_unread_count_and_mark_read(self):
        self._claim()
        conv = Conversation.objects.get()
        self.client.force_authenticate(self.customer)
        self.client.post(
            reverse("chat-send-message", args=[conv.id]),
            {"body": "Hi there"},
            format="json",
        )

        self.client.force_authenticate(self.vendor)
        res = self.client.get(reverse("chat-unread-count"))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["unread_count"], 1)

        res = self.client.post(reverse("chat-conversation-read", args=[conv.id]))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["updated"], 1)
        self.assertTrue(Message.objects.get().is_read)

        res = self.client.get(reverse("chat-unread-count"))
        self.assertEqual(res.data["unread_count"], 0)

    def test_mark_read_does_not_flag_own_messages(self):
        self._claim()
        conv = Conversation.objects.get()
        self.client.force_authenticate(self.customer)
        self.client.post(
            reverse("chat-send-message", args=[conv.id]),
            {"body": "Hello from customer"},
            format="json",
        )

        self.client.force_authenticate(self.customer)
        res = self.client.post(reverse("chat-conversation-read", args=[conv.id]))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["updated"], 0)
        self.assertFalse(Message.objects.get().is_read)
