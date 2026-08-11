from decimal import Decimal

from django.contrib.gis.geos import Point
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from accounts.models import User
from config.tests_base import EagerCeleryTestCase
from restaurants.models import MenuItem, Restaurant
from .models import Cart, CartItem, Order, OrderItem
from .tasks import refresh_stale_carts


def creds(role, username=None):
    return {
        "email": f"{role}@test.com",
        "username": username or role,
        "password": "testpass123",
        "role": role,
        "phone": "+1000000000",
    }


class OrdersTests(EagerCeleryTestCase):
    def setUp(self):
        self.customer = User.objects.create_user(**creds(User.Role.CUSTOMER, "cust"))
        self.vendor = User.objects.create_user(**creds(User.Role.VENDOR))
        self.other_customer = User.objects.create_user(
            **creds(User.Role.CUSTOMER, "other")
        )
        self.other_vendor = User.objects.create_user(**creds(User.Role.VENDOR, "vendor2"))
        self.driver = User.objects.create_user(**creds(User.Role.DRIVER, "driver1"))
        self.other_driver = User.objects.create_user(
            **creds(User.Role.DRIVER, "driver2")
        )
        self.restaurant = Restaurant.objects.create(
            owner=self.vendor,
            name="Burger House",
            address="123 Grill St",
            location=Point(-74.0060, 40.7128, srid=4326),
            status=Restaurant.Status.OPEN,
        )
        self.item1 = MenuItem.objects.create(
            restaurant=self.restaurant,
            name="Classic Burger",
            description="Beef patty",
            price=Decimal("8.99"),
        )
        self.item2 = MenuItem.objects.create(
            restaurant=self.restaurant,
            name="Fries",
            description="Crispy",
            price=Decimal("3.99"),
        )
        self.client.force_authenticate(self.customer)

    def _add_to_cart(self, menu_item_id, quantity=1):
        return self.client.post(
            reverse("cart_item-list"),
            {"menu_item": menu_item_id, "quantity": quantity},
            format="json",
        )

    def _checkout(self, restaurant_id=None, location=True):
        payload = {
            "restaurant": restaurant_id or self.restaurant.id,
            "delivery_address": "456 Customer Ave",
        }
        if location:
            payload["delivery_location"] = {"lat": 40.7130, "lng": -74.0070}
        return self.client.post(reverse("checkout"), payload, format="json")

    def test_add_to_cart_creates_item(self):
        res = self._add_to_cart(self.item1.id, 2)
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(CartItem.objects.count(), 1)
        self.assertEqual(CartItem.objects.first().quantity, 2)
        self.assertEqual(CartItem.objects.first().price_snapshot, Decimal("8.99"))

    def test_add_to_cart_merges_quantity(self):
        self._add_to_cart(self.item1.id, 1)
        self._add_to_cart(self.item1.id, 2)
        self.assertEqual(CartItem.objects.count(), 1)
        self.assertEqual(CartItem.objects.first().quantity, 3)

    def test_add_unavailable_item_rejected(self):
        self.item1.is_available = False
        self.item1.save()
        res = self._add_to_cart(self.item1.id, 1)
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_add_invalid_menu_item_rejected(self):
        res = self._add_to_cart(99999, 1)
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cart_get_creates_cart(self):
        res = self.client.get(reverse("cart"))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(Cart.objects.filter(user=self.customer).count(), 1)

    def test_checkout_empty_cart_rejected(self):
        res = self._checkout()
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_checkout_creates_order_from_cart(self):
        self._add_to_cart(self.item1.id, 2)
        self._add_to_cart(self.item2.id, 1)
        res = self._checkout()
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

        order = Order.objects.get()
        self.assertEqual(order.user, self.customer)
        self.assertEqual(order.restaurant, self.restaurant)
        self.assertEqual(order.status, Order.Status.PENDING)
        self.assertEqual(
            order.total_price,
            Decimal("8.99") * 2 + Decimal("3.99"),
        )
        self.assertEqual(order.items.count(), 2)
        self.assertTrue(order.delivery_location is not None)

        snap = OrderItem.objects.get(menu_item=self.item1)
        self.assertEqual(snap.price_snapshot, Decimal("8.99"))
        self.assertEqual(snap.quantity, 2)

        self.assertEqual(CartItem.objects.filter(cart__user=self.customer).count(), 0)

    def test_checkout_rejects_cross_restaurant_cart(self):
        other_restaurant = Restaurant.objects.create(
            owner=self.vendor,
            name="Pizza Palace",
            address="456 Oven Ave",
            status=Restaurant.Status.OPEN,
        )
        self._add_to_cart(self.item1.id, 1)
        res = self._checkout(restaurant_id=other_restaurant.id)
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_order_list_only_own_orders(self):
        Order.objects.create(
            user=self.other_customer,
            restaurant=self.restaurant,
            delivery_address="x",
            status=Order.Status.PENDING,
        )
        self._add_to_cart(self.item1.id, 1)
        self._checkout()
        res = self.client.get(reverse("order-list"))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        ids = [o["id"] for o in res.data["results"]]
        self.assertEqual(len(ids), 1)
        self.assertEqual(Order.objects.get(id=ids[0]).user, self.customer)

    def test_cancel_pending_order(self):
        self._add_to_cart(self.item1.id, 1)
        res = self._checkout()
        order_id = res.data["id"]
        res = self.client.post(reverse("order-cancel", args=[order_id]))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(Order.objects.get(id=order_id).status, Order.Status.CANCELLED)

    def test_cancel_delivered_order_rejected(self):
        order = Order.objects.create(
            user=self.customer,
            restaurant=self.restaurant,
            delivery_address="x",
            status=Order.Status.DELIVERED,
        )
        res = self.client.post(reverse("order-cancel", args=[order.id]))
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cancel_other_users_order_not_found(self):
        order = Order.objects.create(
            user=self.other_customer,
            restaurant=self.restaurant,
            delivery_address="x",
            status=Order.Status.PENDING,
        )
        res = self.client.post(reverse("order-cancel", args=[order.id]))
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_state_machine_allows_pending_to_accepted(self):
        order = Order.objects.create(
            user=self.customer,
            restaurant=self.restaurant,
            delivery_address="x",
            status=Order.Status.PENDING,
        )
        order.status = Order.Status.ACCEPTED
        order.save()
        self.assertEqual(Order.objects.get(id=order.id).status, Order.Status.ACCEPTED)
        self.assertIsNotNone(Order.objects.get(id=order.id).accepted_at)

    def test_state_machine_blocks_delivered_to_accepted(self):
        order = Order.objects.create(
            user=self.customer,
            restaurant=self.restaurant,
            delivery_address="x",
            status=Order.Status.DELIVERED,
        )
        order.status = Order.Status.ACCEPTED
        with self.assertRaises(ValidationError):
            order.save()

    def test_state_machine_blocks_cancelled_to_anything(self):
        order = Order.objects.create(
            user=self.customer,
            restaurant=self.restaurant,
            delivery_address="x",
            status=Order.Status.CANCELLED,
        )
        order.status = Order.Status.PENDING
        with self.assertRaises(ValidationError):
            order.save()

    def test_full_lifecycle_transitions(self):
        order = Order.objects.create(
            user=self.customer,
            restaurant=self.restaurant,
            delivery_address="x",
            status=Order.Status.PENDING,
        )
        for nxt in (
            Order.Status.ACCEPTED,
            Order.Status.PREPARING,
            Order.Status.READY,
            Order.Status.PICKED_UP,
            Order.Status.DELIVERED,
        ):
            order.status = nxt
            order.save()
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.DELIVERED)
        self.assertIsNotNone(order.delivered_at)

    def test_vendor_lists_only_own_restaurant_orders(self):
        other_restaurant = Restaurant.objects.create(
            owner=self.other_vendor,
            name="Other Vendor Place",
            address="789 Other St",
            status=Restaurant.Status.OPEN,
        )
        own_order = Order.objects.create(
            user=self.customer,
            restaurant=self.restaurant,
            delivery_address="x",
            status=Order.Status.PENDING,
        )
        Order.objects.create(
            user=self.customer,
            restaurant=other_restaurant,
            delivery_address="y",
            status=Order.Status.PENDING,
        )

        self.client.force_authenticate(self.vendor)
        res = self.client.get(reverse("vendor-orders"))

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        ids = [o["id"] for o in res.data]
        self.assertEqual(ids, [own_order.id])

    def test_vendor_can_advance_order_status(self):
        order = Order.objects.create(
            user=self.customer,
            restaurant=self.restaurant,
            delivery_address="x",
            status=Order.Status.PENDING,
        )

        self.client.force_authenticate(self.vendor)
        for nxt in (Order.Status.ACCEPTED, Order.Status.PREPARING, Order.Status.READY):
            res = self.client.post(
                reverse("vendor-order-status", args=[order.id]),
                {"status": nxt},
                format="json",
            )
            self.assertEqual(res.status_code, status.HTTP_200_OK)

        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.READY)

    def test_vendor_cannot_manage_other_vendor_order(self):
        other_restaurant = Restaurant.objects.create(
            owner=self.other_vendor,
            name="Other Vendor Place",
            address="789 Other St",
            status=Restaurant.Status.OPEN,
        )
        order = Order.objects.create(
            user=self.customer,
            restaurant=other_restaurant,
            delivery_address="x",
            status=Order.Status.PENDING,
        )

        self.client.force_authenticate(self.vendor)
        res = self.client.post(
            reverse("vendor-order-status", args=[order.id]),
            {"status": Order.Status.ACCEPTED},
            format="json",
        )

        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_driver_full_flow_claim_pickup_deliver(self):
        order = Order.objects.create(
            user=self.customer,
            restaurant=self.restaurant,
            delivery_address="x",
            status=Order.Status.READY,
        )

        self.client.force_authenticate(self.driver)

        claim_res = self.client.post(reverse("driver-order-claim", args=[order.id]))
        self.assertEqual(claim_res.status_code, status.HTTP_200_OK)

        pickup_res = self.client.post(reverse("driver-order-picked-up", args=[order.id]))
        self.assertEqual(pickup_res.status_code, status.HTTP_200_OK)

        deliver_res = self.client.post(reverse("driver-order-delivered", args=[order.id]))
        self.assertEqual(deliver_res.status_code, status.HTTP_200_OK)

        order.refresh_from_db()
        self.assertEqual(order.driver, self.driver)
        self.assertEqual(order.status, Order.Status.DELIVERED)

    def test_driver_available_orders_only_ready_unclaimed(self):
        ready_unclaimed = Order.objects.create(
            user=self.customer,
            restaurant=self.restaurant,
            delivery_address="x",
            status=Order.Status.READY,
        )
        Order.objects.create(
            user=self.customer,
            restaurant=self.restaurant,
            delivery_address="y",
            status=Order.Status.PICKED_UP,
            driver=self.driver,
        )
        Order.objects.create(
            user=self.customer,
            restaurant=self.restaurant,
            delivery_address="z",
            status=Order.Status.READY,
            driver=self.other_driver,
        )

        self.client.force_authenticate(self.driver)
        res = self.client.get(reverse("driver-orders-available"))

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        ids = [o["id"] for o in res.data]
        self.assertEqual(ids, [ready_unclaimed.id])

    def test_other_driver_cannot_pickup_claimed_order(self):
        order = Order.objects.create(
            user=self.customer,
            restaurant=self.restaurant,
            delivery_address="x",
            status=Order.Status.READY,
        )

        self.client.force_authenticate(self.driver)
        self.client.post(reverse("driver-order-claim", args=[order.id]))

        self.client.force_authenticate(self.other_driver)
        res = self.client.post(reverse("driver-order-picked-up", args=[order.id]))

        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_driver_lists_only_own_assigned_orders(self):
        own_order = Order.objects.create(
            user=self.customer,
            restaurant=self.restaurant,
            delivery_address="x",
            status=Order.Status.PICKED_UP,
            driver=self.driver,
        )
        Order.objects.create(
            user=self.customer,
            restaurant=self.restaurant,
            delivery_address="y",
            status=Order.Status.READY,
            driver=self.other_driver,
        )
        Order.objects.create(
            user=self.customer,
            restaurant=self.restaurant,
            delivery_address="z",
            status=Order.Status.READY,
        )

        self.client.force_authenticate(self.driver)
        res = self.client.get(reverse("driver-orders"))

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        ids = [o["id"] for o in res.data]
        self.assertEqual(ids, [own_order.id])

    def test_driver_can_fetch_own_order_detail(self):
        order = Order.objects.create(
            user=self.customer,
            restaurant=self.restaurant,
            delivery_address="x",
            status=Order.Status.PICKED_UP,
            driver=self.driver,
        )

        self.client.force_authenticate(self.driver)
        res = self.client.get(reverse("driver-order-detail", args=[order.id]))

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["id"], order.id)

    def test_driver_cannot_fetch_other_driver_order_detail(self):
        order = Order.objects.create(
            user=self.customer,
            restaurant=self.restaurant,
            delivery_address="x",
            status=Order.Status.PICKED_UP,
            driver=self.other_driver,
        )

        self.client.force_authenticate(self.driver)
        res = self.client.get(reverse("driver-order-detail", args=[order.id]))

        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_driver_orders_endpoints_forbidden_for_non_driver(self):
        self.client.force_authenticate(self.customer)
        res = self.client.get(reverse("driver-orders"))
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        res = self.client.get(reverse("driver-order-detail", args=[1]))
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_driver_updates_location(self):
        self.client.force_authenticate(self.driver)
        res = self.client.patch(
            reverse("driver-location"),
            {"location": {"lat": 40.7135, "lng": -74.0080}},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.driver.refresh_from_db()
        self.assertIsNotNone(self.driver.location)
        self.assertEqual(self.driver.location.y, 40.7135)
        self.assertEqual(self.driver.location.x, -74.0080)
        self.assertEqual(res.data["location"], {"lat": 40.7135, "lng": -74.008})

    def test_driver_updates_availability_with_location(self):
        self.client.force_authenticate(self.driver)
        res = self.client.patch(
            reverse("driver-location"),
            {"location": {"lat": 40.7135, "lng": -74.0080}, "is_available": False},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.driver.refresh_from_db()
        self.assertFalse(self.driver.is_available)

    def test_driver_location_requires_valid_coords(self):
        self.client.force_authenticate(self.driver)
        res = self.client.patch(
            reverse("driver-location"),
            {"location": {"lat": 999, "lng": -74.0080}},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_driver_location_forbidden_for_non_driver(self):
        self.client.force_authenticate(self.vendor)
        res = self.client.patch(
            reverse("driver-location"),
            {"location": {"lat": 40.7135, "lng": -74.0080}},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_driver_location_requires_auth(self):
        self.client.logout()
        res = self.client.patch(
            reverse("driver-location"),
            {"location": {"lat": 40.7135, "lng": -74.0080}},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)


class RefreshStaleCartsTests(EagerCeleryTestCase):
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

    def _make_stale_cart(self, hours=25):
        cart = Cart.objects.create(user=self.customer)
        CartItem.objects.create(
            cart=cart,
            menu_item=self.item,
            quantity=1,
            price_snapshot=self.item.price,
        )
        Cart.objects.filter(pk=cart.pk).update(
            updated_at=timezone.now() - timezone.timedelta(hours=hours)
        )
        return Cart.objects.get(pk=cart.pk)

    def test_updates_price_snapshot_for_stale_cart(self):
        self._make_stale_cart()
        self.item.price = Decimal("9.49")
        self.item.save()

        result = refresh_stale_carts()

        self.assertEqual(result["refreshed_carts"], 1)
        item = CartItem.objects.get()
        self.assertEqual(item.price_snapshot, Decimal("9.49"))

    def test_removes_unavailable_item_for_stale_cart(self):
        self._make_stale_cart()
        self.item.is_available = False
        self.item.save()

        result = refresh_stale_carts()

        self.assertEqual(result["refreshed_carts"], 1)
        self.assertEqual(CartItem.objects.count(), 0)

    def test_leaves_fresh_cart_untouched(self):
        self._make_stale_cart(hours=1)
        self.item.price = Decimal("9.49")
        self.item.save()

        result = refresh_stale_carts()

        self.assertEqual(result["refreshed_carts"], 0)
        item = CartItem.objects.get()
        self.assertEqual(item.price_snapshot, Decimal("8.99"))

    def test_keeps_unchanged_stale_cart_intact(self):
        self._make_stale_cart()

        result = refresh_stale_carts()

        self.assertEqual(result["refreshed_carts"], 0)
        self.assertEqual(CartItem.objects.count(), 1)
        self.assertEqual(CartItem.objects.get().price_snapshot, Decimal("8.99"))

    def test_resets_updated_at_after_refresh(self):
        cart = self._make_stale_cart()
        self.item.price = Decimal("9.49")
        self.item.save()

        refresh_stale_carts()
        cart.refresh_from_db()
        self.assertGreater(cart.updated_at, timezone.now() - timezone.timedelta(hours=1))
