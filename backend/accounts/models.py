from django.contrib.auth.models import AbstractUser
from django.contrib.gis.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        CUSTOMER = "CUSTOMER", "Customer"
        VENDOR = "VENDOR", "Vendor"
        DRIVER = "DRIVER", "Driver"
        ADMIN = "ADMIN", "Admin"

    role = models.CharField(max_length=10, choices=Role.choices, default=Role.CUSTOMER)
    phone = models.CharField(max_length=20, blank=True)
    location = models.PointField(geography=True, blank=True, null=True)
    is_available = models.BooleanField(default=True)
    avg_rating = models.FloatField(default=0.0)
    rating_count = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"{self.email or self.username} ({self.role})"
