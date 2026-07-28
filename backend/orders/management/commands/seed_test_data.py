from datetime import timedelta
from decimal import Decimal

from django.contrib.gis.geos import Point
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounts.models import User
from orders.models import Cart, CartItem, Order, OrderItem
from restaurants.models import MenuItem, Restaurant


class Command(BaseCommand):
    help = "Populate local DB with users, carts, and realistic sample orders"

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write("Seeding restaurant and menu data...")
        call_command("seed_restaurants")

        self.stdout.write("Seeding users...")
        users = self._seed_users()

        self.stdout.write("Seeding carts...")
        self._seed_carts(users)

        self.stdout.write("Seeding orders...")
        self._seed_orders(users)

        self.stdout.write(self.style.SUCCESS("Seed data completed."))

    def _upsert_user(self, *, username, email, role, phone, password):
        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                "email": email,
                "role": role,
                "phone": phone,
            },
        )

        if not created:
            changed = False
            if user.email != email:
                user.email = email
                changed = True
            if user.role != role:
                user.role = role
                changed = True
            if user.phone != phone:
                user.phone = phone
                changed = True
            if changed:
                user.save(update_fields=["email", "role", "phone"])

        user.set_password(password)
        user.save(update_fields=["password"])
        return user

    def _seed_users(self):
        vendor = User.objects.get(username="vendor")

        users = {
            "vendor": vendor,
            "vendor2": self._upsert_user(
                username="vendor2",
                email="vendor2@test.com",
                role=User.Role.VENDOR,
                phone="+2222222223",
                password="testpass123",
            ),
            "customer1": self._upsert_user(
                username="customer1",
                email="customer1@test.com",
                role=User.Role.CUSTOMER,
                phone="+1111111111",
                password="testpass123",
            ),
            "customer2": self._upsert_user(
                username="customer2",
                email="customer2@test.com",
                role=User.Role.CUSTOMER,
                phone="+1111111112",
                password="testpass123",
            ),
            "driver1": self._upsert_user(
                username="driver1",
                email="driver1@test.com",
                role=User.Role.DRIVER,
                phone="+3333333333",
                password="testpass123",
            ),
        }

        return users

    def _seed_carts(self, users):
        restaurants = list(Restaurant.objects.order_by("id"))
        if len(restaurants) < 2:
            raise RuntimeError("Need at least 2 restaurants to seed cart data.")

        cart_specs = [
            (users["customer1"], restaurants[0], [("Classic Burger", 2), ("Fries", 1)]),
            (users["customer2"], restaurants[1], [("Margherita", 1), ("Garlic Bread", 2)]),
        ]

        for user, restaurant, item_specs in cart_specs:
            cart, _ = Cart.objects.get_or_create(user=user)
            cart.items.all().delete()

            for item_name, quantity in item_specs:
                menu_item = MenuItem.objects.get(restaurant=restaurant, name=item_name)
                CartItem.objects.create(
                    cart=cart,
                    menu_item=menu_item,
                    quantity=quantity,
                    price_snapshot=menu_item.price,
                )

    def _seed_orders(self, users):
        now = timezone.now()
        one_hour = timedelta(hours=1)

        Order.objects.filter(delivery_address__startswith="Seed Order:").delete()

        burger_house = Restaurant.objects.get(name="Burger House")
        pizza_palace = Restaurant.objects.get(name="Pizza Palace")

        classic_burger = MenuItem.objects.get(
            restaurant=burger_house, name="Classic Burger"
        )
        fries = MenuItem.objects.get(restaurant=burger_house, name="Fries")
        margherita = MenuItem.objects.get(restaurant=pizza_palace, name="Margherita")
        garlic_bread = MenuItem.objects.get(restaurant=pizza_palace, name="Garlic Bread")

        self._create_order(
            customer=users["customer1"],
            restaurant=burger_house,
            status=Order.Status.PENDING,
            item_rows=[(classic_burger, 1), (fries, 2)],
            address="Seed Order: Pending",
            location=Point(-74.0001, 40.7101, srid=4326),
            created_at=now - one_hour,
        )

        self._create_order(
            customer=users["customer1"],
            restaurant=pizza_palace,
            status=Order.Status.READY,
            item_rows=[(margherita, 2)],
            address="Seed Order: Ready",
            location=Point(-74.0020, 40.7112, srid=4326),
            created_at=now - (2 * one_hour),
            accepted_at=now - timedelta(minutes=110),
            preparing_at=now - timedelta(minutes=100),
            ready_at=now - timedelta(minutes=80),
        )

        self._create_order(
            customer=users["customer2"],
            restaurant=burger_house,
            status=Order.Status.DELIVERED,
            item_rows=[(classic_burger, 1), (fries, 1)],
            address="Seed Order: Delivered",
            location=Point(-74.0040, 40.7125, srid=4326),
            created_at=now - (5 * one_hour),
            accepted_at=now - timedelta(minutes=290),
            preparing_at=now - timedelta(minutes=275),
            ready_at=now - timedelta(minutes=255),
            picked_up_at=now - timedelta(minutes=245),
            delivered_at=now - timedelta(minutes=225),
        )

        self._create_order(
            customer=users["customer2"],
            restaurant=pizza_palace,
            status=Order.Status.CANCELLED,
            item_rows=[(margherita, 1), (garlic_bread, 1)],
            address="Seed Order: Cancelled",
            location=Point(-74.0060, 40.7130, srid=4326),
            created_at=now - (3 * one_hour),
            cancelled_at=now - timedelta(minutes=170),
        )

    def _create_order(
        self,
        *,
        customer,
        restaurant,
        status,
        item_rows,
        address,
        location,
        created_at,
        accepted_at=None,
        preparing_at=None,
        ready_at=None,
        picked_up_at=None,
        delivered_at=None,
        cancelled_at=None,
    ):
        order = Order.objects.create(
            user=customer,
            restaurant=restaurant,
            status=status,
            total_price=Decimal("0.00"),
            delivery_address=address,
            delivery_location=location,
            accepted_at=accepted_at,
            preparing_at=preparing_at,
            ready_at=ready_at,
            picked_up_at=picked_up_at,
            delivered_at=delivered_at,
            cancelled_at=cancelled_at,
        )

        total = Decimal("0.00")
        for menu_item, quantity in item_rows:
            OrderItem.objects.create(
                order=order,
                menu_item=menu_item,
                quantity=quantity,
                price_snapshot=menu_item.price,
            )
            total += menu_item.price * quantity

        Order.objects.filter(pk=order.pk).update(total_price=total, created_at=created_at)
