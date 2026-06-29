from django.core.management.base import BaseCommand
from accounts.models import User


class Command(BaseCommand):
    help = "Seed test users (one per role)"

    def handle(self, *args, **options):
        users_data = [
            {
                "email": "customer@test.com",
                "username": "customer",
                "role": User.Role.CUSTOMER,
                "phone": "+1111111111",
            },
            {
                "email": "vendor@test.com",
                "username": "vendor",
                "role": User.Role.VENDOR,
                "phone": "+2222222222",
            },
            {
                "email": "driver@test.com",
                "username": "driver",
                "role": User.Role.DRIVER,
                "phone": "+3333333333",
            },
        ]
        for data in users_data:
            email = data["email"]
            if not User.objects.filter(email=email).exists():
                User.objects.create_user(**data, password="testpass123")
                self.stdout.write(
                    self.style.SUCCESS(f"Created {data['role']}: {email}")
                )
            else:
                self.stdout.write(f"Skipped {email} (already exists)")
