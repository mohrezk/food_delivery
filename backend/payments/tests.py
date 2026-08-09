from decimal import Decimal
from unittest.mock import patch

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User
from payments.models import Payment
from payments.services import MockPaymentService
from restaurants.models import MenuItem, Restaurant
from orders.models import Order, Cart, CartItem


def creds(role, username=None):
    return {
        "email": f"{role}@test.com",
        "username": username or role,
        "password": "testpass123",
        "role": role,
        "phone": "+1000000000",
    }


class PaymentsTests(APITestCase):
    def setUp(self):
        self.customer = User.objects.create_user(**creds(User.Role.CUSTOMER, "cust"))
        self.vendor = User.objects.create_user(**creds(User.Role.VENDOR))
        self.admin = User.objects.create_user(**creds(User.Role.ADMIN, "admin"))
        self.other_customer = User.objects.create_user(
            **creds(User.Role.CUSTOMER, "other")
        )
        self.restaurant = Restaurant.objects.create(
            owner=self.vendor,
            name="Burger House",
            address="123 Grill St",
            status=Restaurant.Status.OPEN,
        )
        self.item = MenuItem.objects.create(
            restaurant=self.restaurant,
            name="Classic Burger",
            description="Beef patty",
            price=Decimal("8.99"),
        )
        self.client.force_authenticate(self.customer)

    def _checkout(self):
        cart, _ = Cart.objects.get_or_create(user=self.customer)
        CartItem.objects.create(
            cart=cart,
            menu_item=self.item,
            quantity=1,
            price_snapshot=self.item.price,
        )
        payload = {
            "restaurant": self.restaurant.id,
            "delivery_address": "456 Customer Ave",
        }
        return self.client.post(reverse("checkout"), payload, format="json")

    def test_checkout_creates_payment(self):
        res = self._checkout()
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        order = Order.objects.get(pk=res.data["id"])
        self.assertTrue(hasattr(order, "payment"))
        self.assertEqual(order.payment.amount, order.total_price)
        self.assertIn(order.payment.status, (Payment.Status.SUCCEEDED, Payment.Status.FAILED))

    def test_payment_detail_owner_can_view(self):
        res = self._checkout()
        order = Order.objects.get(pk=res.data["id"])
        payment = order.payment

        res = self.client.get(reverse("payment-detail", args=[order.id]))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["id"], payment.id)
        self.assertEqual(res.data["amount"], str(payment.amount))

    def test_payment_detail_other_customer_forbidden(self):
        res = self._checkout()
        order = Order.objects.get(pk=res.data["id"])

        self.client.force_authenticate(self.other_customer)
        res = self.client.get(reverse("payment-detail", args=[order.id]))
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_payment_detail_admin_can_view(self):
        res = self._checkout()
        order = Order.objects.get(pk=res.data["id"])

        self.client.force_authenticate(self.admin)
        res = self.client.get(reverse("payment-detail", args=[order.id]))
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_payment_detail_requires_authentication(self):
        self.client.logout()
        res = self.client.get(reverse("payment-detail", args=[1]))
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)


class MockPaymentServiceTests(APITestCase):
    def setUp(self):
        self.customer = User.objects.create_user(**creds(User.Role.CUSTOMER, "cust"))
        self.vendor = User.objects.create_user(**creds(User.Role.VENDOR))
        self.restaurant = Restaurant.objects.create(
            owner=self.vendor,
            name="Burger House",
            address="123 Grill St",
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
            delivery_address="456 Customer Ave",
            status=Order.Status.PENDING,
            total_price=Decimal("8.99"),
        )

    def test_create_payment_sets_amount_and_method(self):
        service = MockPaymentService()
        payment = service.create_payment(self.order)

        self.assertEqual(payment.order, self.order)
        self.assertEqual(payment.amount, Decimal("8.99"))
        self.assertEqual(payment.method, "mock")
        self.assertIn(payment.status, (Payment.Status.SUCCEEDED, Payment.Status.FAILED))

    def test_create_payment_sets_gateway_response(self):
        service = MockPaymentService()
        payment = service.create_payment(self.order)

        self.assertIn("provider", payment.gateway_response)
        self.assertEqual(payment.gateway_response["provider"], "mock")
        self.assertIn("transaction_id", payment.gateway_response)

    def test_capture_payment_changes_status_to_succeeded(self):
        payment = Payment.objects.create(
            order=self.order,
            amount=Decimal("8.99"),
            status=Payment.Status.PENDING,
        )
        service = MockPaymentService()
        updated = service.capture_payment(payment)

        self.assertEqual(updated.status, Payment.Status.SUCCEEDED)
        self.assertTrue(updated.gateway_response.get("captured"))

    def test_capture_payment_idempotent_on_succeeded(self):
        payment = Payment.objects.create(
            order=self.order,
            amount=Decimal("8.99"),
            status=Payment.Status.SUCCEEDED,
        )
        service = MockPaymentService()
        updated = service.capture_payment(payment)

        self.assertEqual(updated.status, Payment.Status.SUCCEEDED)

    def test_refund_payment_changes_status_to_refunded(self):
        payment = Payment.objects.create(
            order=self.order,
            amount=Decimal("8.99"),
            status=Payment.Status.SUCCEEDED,
        )
        service = MockPaymentService()
        updated = service.refund_payment(payment)

        self.assertEqual(updated.status, Payment.Status.REFUNDED)
        self.assertTrue(updated.gateway_response.get("refunded"))

    def test_refund_payment_idempotent_on_refunded(self):
        payment = Payment.objects.create(
            order=self.order,
            amount=Decimal("8.99"),
            status=Payment.Status.REFUNDED,
        )
        service = MockPaymentService()
        updated = service.refund_payment(payment)

        self.assertEqual(updated.status, Payment.Status.REFUNDED)

    @patch("payments.services.random.random", return_value=0.5)
    def test_create_payment_respects_success_rate(self, mock_random):
        service = MockPaymentService()
        payment = service.create_payment(self.order)

        self.assertEqual(payment.status, Payment.Status.SUCCEEDED)
        mock_random.assert_called()

    @patch("payments.services.random.random", return_value=0.95)
    def test_create_payment_fails_when_random_above_threshold(self, mock_random):
        service = MockPaymentService()
        payment = service.create_payment(self.order)

        self.assertEqual(payment.status, Payment.Status.FAILED)
        mock_random.assert_called()
