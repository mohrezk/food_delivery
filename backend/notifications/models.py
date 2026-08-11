from django.contrib.gis.db import models

from accounts.models import User
from orders.models import Order


class Notification(models.Model):
    class Type(models.TextChoices):
        ORDER = "ORDER", "Order"
        CHAT = "CHAT", "Chat"
        SYSTEM = "SYSTEM", "System"

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    type = models.CharField(max_length=20, choices=Type.choices, default=Type.SYSTEM)
    title = models.CharField(max_length=255)
    message = models.TextField()
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="notifications",
        blank=True,
        null=True,
    )
    is_read = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.type} for user {self.user_id}: {self.title}"
