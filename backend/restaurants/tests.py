from decimal import Decimal

from django.contrib.gis.geos import Point
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User
from restaurants.models import MenuItem, Restaurant


def user_payload(role, username=None):
    return {
        "email": f"{role.lower()}_{username or role.lower()}@test.com",
        "username": username or role.lower(),
        "password": "testpass123",
        "role": role,
        "phone": "+1000000000",
    }


class RestaurantsTests(APITestCase):
    def setUp(self):
        self.vendor = User.objects.create_user(**user_payload(User.Role.VENDOR, "vendor"))
        self.other_vendor = User.objects.create_user(
            **user_payload(User.Role.VENDOR, "other_vendor")
        )
        self.customer = User.objects.create_user(
            **user_payload(User.Role.CUSTOMER, "customer")
        )
        self.restaurant = Restaurant.objects.create(
            owner=self.vendor,
            name="Burger House",
            address="123 Grill St",
            location=Point(-74.0060, 40.7128, srid=4326),
            status=Restaurant.Status.OPEN,
        )
        self.second_restaurant = Restaurant.objects.create(
            owner=self.vendor,
            name="Pizza Place",
            address="456 Oven Ave",
            location=Point(-74.0070, 40.7130, srid=4326),
            status=Restaurant.Status.OPEN,
        )
        self.item = MenuItem.objects.create(
            restaurant=self.restaurant,
            name="Classic Burger",
            description="Beef patty",
            price=Decimal("8.99"),
        )

    def test_restaurant_list_is_public(self):
        res = self.client.get(reverse("restaurant-list"))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(res.data["count"], 1)

    def test_restaurant_create_requires_vendor(self):
        self.client.force_authenticate(self.customer)
        payload = {"name": "Nope", "address": "x"}

        res = self.client.post(reverse("restaurant-list"), payload, format="json")

        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_vendor_can_create_restaurant_owner_is_forced(self):
        self.client.force_authenticate(self.vendor)
        payload = {
            "owner": self.other_vendor.id,
            "name": "Pizza Place",
            "address": "456 Oven Ave",
            "location": {"lat": 40.7130, "lng": -74.0070},
        }

        res = self.client.post(reverse("restaurant-list"), payload, format="json")

        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        created = Restaurant.objects.get(id=res.data["id"])
        self.assertEqual(created.owner, self.vendor)

    def test_restaurant_create_rejects_invalid_location(self):
        self.client.force_authenticate(self.vendor)
        payload = {
            "name": "Bad Geo",
            "address": "Nowhere",
            "location": {"lat": 100.0, "lng": -74.0},
        }

        res = self.client.post(reverse("restaurant-list"), payload, format="json")

        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("location", res.data)

    def test_non_owner_cannot_update_restaurant(self):
        self.client.force_authenticate(self.other_vendor)

        res = self.client.patch(
            reverse("restaurant-detail", args=[self.restaurant.id]),
            {"name": "Renamed"},
            format="json",
        )

        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_owner_can_update_restaurant(self):
        self.client.force_authenticate(self.vendor)

        res = self.client.patch(
            reverse("restaurant-detail", args=[self.restaurant.id]),
            {"name": "Renamed"},
            format="json",
        )

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.restaurant.refresh_from_db()
        self.assertEqual(self.restaurant.name, "Renamed")

    def test_menu_item_create_requires_vendor(self):
        self.client.force_authenticate(self.customer)
        payload = {
            "restaurant": self.restaurant.id,
            "name": "Fries",
            "description": "Crispy",
            "price": "3.99",
        }

        res = self.client.post(reverse("item-list"), payload, format="json")

        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_vendor_cannot_create_menu_item_for_other_vendor_restaurant(self):
        self.client.force_authenticate(self.other_vendor)
        payload = {
            "restaurant": self.restaurant.id,
            "name": "Fries",
            "description": "Crispy",
            "price": "3.99",
        }

        res = self.client.post(reverse("item-list"), payload, format="json")

        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_owner_can_create_menu_item(self):
        self.client.force_authenticate(self.vendor)
        payload = {
            "restaurant": self.restaurant.id,
            "name": "Fries",
            "description": "Crispy",
            "price": "3.99",
        }

        res = self.client.post(reverse("item-list"), payload, format="json")

        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            MenuItem.objects.filter(restaurant=self.restaurant, name="Fries").count(),
            1,
        )

    def test_non_owner_cannot_update_menu_item(self):
        self.client.force_authenticate(self.other_vendor)

        res = self.client.patch(
            reverse("item-detail", args=[self.item.id]),
            {"price": "9.99"},
            format="json",
        )

        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_owner_cannot_reassign_menu_item_to_another_restaurant(self):
        self.client.force_authenticate(self.vendor)

        res = self.client.patch(
            reverse("item-detail", args=[self.item.id]),
            {"restaurant": self.second_restaurant.id},
            format="json",
        )

        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.item.refresh_from_db()
        self.assertEqual(self.item.restaurant_id, self.restaurant.id)
