from decimal import Decimal

from django.contrib.gis.geos import Point
from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import User
from restaurants.models import Restaurant, MenuItem


class Command(BaseCommand):
    help = "Seed restaurants and menu items for testing"

    @transaction.atomic
    def handle(self, *args, **options):
        vendor, created = User.objects.get_or_create(
            email="vendor@test.com",
            defaults={
                "username": "vendor",
                "role": User.Role.VENDOR,
                "phone": "+2222222222",
            },
        )
        if created:
            vendor.set_password("testpass123")
            vendor.save()
            self.stdout.write(self.style.SUCCESS("Created vendor: vendor@test.com"))
        else:
            self.stdout.write("Skipped vendor (already exists)")

        restaurants_data = [
            {
                "name": "Burger House",
                "address": "123 Grill St, Food City",
                "lat": 40.7128,
                "lng": -74.0060,
                "items": [
                    {
                        "name": "Classic Burger",
                        "description": "Beef patty, lettuce, tomato",
                        "price": "8.99",
                    },
                    {
                        "name": "Cheese Burger",
                        "description": "Cheddar, beef patty",
                        "price": "10.49",
                    },
                    {
                        "name": "Fries",
                        "description": "Crispy golden fries",
                        "price": "3.99",
                    },
                    {
                        "name": "Milkshake",
                        "description": "Vanilla milkshake",
                        "price": "4.99",
                    },
                ],
            },
            {
                "name": "Pizza Palace",
                "address": "456 Oven Ave, Food City",
                "lat": 40.7138,
                "lng": -74.0070,
                "items": [
                    {
                        "name": "Margherita",
                        "description": "Tomato, mozzarella, basil",
                        "price": "12.99",
                    },
                    {
                        "name": "Pepperoni",
                        "description": "Pepperoni, mozzarella",
                        "price": "14.99",
                    },
                    {
                        "name": "Garlic Bread",
                        "description": "Toasted with garlic butter",
                        "price": "5.49",
                    },
                ],
            },
            {
                "name": "Sushi Spot",
                "address": "789 Roll Rd, Food City",
                "lat": 40.7148,
                "lng": -74.0080,
                "items": [
                    {"name": "Salmon Roll", "description": "8 pieces", "price": "9.99"},
                    {
                        "name": "Tuna Nigiri",
                        "description": "6 pieces",
                        "price": "11.99",
                    },
                    {
                        "name": "Miso Soup",
                        "description": "Tofu, seaweed, scallions",
                        "price": "3.49",
                    },
                ],
            },
        ]

        for rdata in restaurants_data:
            restaurant, r_created = Restaurant.objects.get_or_create(
                name=rdata["name"],
                defaults={
                    "owner": vendor,
                    "address": rdata["address"],
                    "location": Point(rdata["lng"], rdata["lat"], srid=4326),
                    "status": Restaurant.Status.OPEN,
                },
            )
            if r_created:
                self.stdout.write(
                    self.style.SUCCESS(f"Created restaurant: {restaurant.name}")
                )
            else:
                self.stdout.write(
                    f"Skipped restaurant (already exists): {restaurant.name}"
                )

            for idata in rdata["items"]:
                item, i_created = MenuItem.objects.get_or_create(
                    restaurant=restaurant,
                    name=idata["name"],
                    defaults={
                        "description": idata["description"],
                        "price": Decimal(idata["price"]),
                        "is_available": True,
                    },
                )
                if i_created:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"  Created menu item: {item.name} ({item.price})"
                        )
                    )
                else:
                    self.stdout.write(
                        f"  Skipped menu item (already exists): {item.name}"
                    )
