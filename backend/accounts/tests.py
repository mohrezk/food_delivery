from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User


def user_payload(role=User.Role.CUSTOMER, username="user", email=None):
    return {
        "email": email or f"{username}@test.com",
        "username": username,
        "password": "testpass123",
        "role": role,
        "phone": "+1000000000",
    }


class AccountsTests(APITestCase):
    def test_register_creates_user(self):
        payload = user_payload(username="newcustomer")
        res = self.client.post(reverse("register"), payload, format="json")

        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(User.objects.count(), 1)
        self.assertNotIn("password", res.data)
        self.assertEqual(User.objects.get().role, User.Role.CUSTOMER)

    def test_register_rejects_admin_role(self):
        payload = user_payload(role=User.Role.ADMIN, username="hacker")
        res = self.client.post(reverse("register"), payload, format="json")

        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(User.objects.count(), 0)
        self.assertIn("role", res.data)

    def test_login_returns_tokens(self):
        creds = user_payload(username="authuser")
        User.objects.create_user(**creds)

        res = self.client.post(
            reverse("login"),
            {"username": creds["username"], "password": creds["password"]},
            format="json",
        )

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn("access", res.data)
        self.assertIn("refresh", res.data)

    def test_me_requires_authentication(self):
        res = self.client.get(reverse("me"))
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_me_returns_current_user(self):
        user = User.objects.create_user(**user_payload(username="current"))
        self.client.force_authenticate(user)

        res = self.client.get(reverse("me"))

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["id"], user.id)
        self.assertEqual(res.data["username"], "current")

    def test_me_updates_location(self):
        user = User.objects.create_user(**user_payload(username="geo"))
        self.client.force_authenticate(user)

        res = self.client.patch(
            reverse("me"),
            {"location": {"lat": 40.7128, "lng": -74.006}},
            format="json",
        )

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        user.refresh_from_db()
        self.assertIsNotNone(user.location)
        self.assertAlmostEqual(user.location.y, 40.7128, places=4)
        self.assertAlmostEqual(user.location.x, -74.006, places=4)
