from django.contrib.gis.db import models
from django.core.exceptions import ValidationError
from django.db import transaction

from accounts.models import User
from restaurants.models import Restaurant, MenuItem


class Cart(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="cart")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    menu_item = models.ForeignKey(
        MenuItem, on_delete=models.CASCADE, related_name="cart_items"
    )

    quantity = models.PositiveIntegerField(default=1)

    price_snapshot = models.DecimalField(
        max_digits=10,
        decimal_places=2,
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["cart", "menu_item"],
                name="unique_item_per_cart",
            )
        ]


class Order(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        ACCEPTED = "ACCEPTED", "Accepted"
        PREPARING = "PREPARING", "Preparing"
        READY = "READY", "Ready"
        PICKED_UP = "PICKED_UP", "Picked Up"
        DELIVERED = "DELIVERED", "Delivered"
        CANCELLED = "CANCELLED", "Cancelled"
        EXPIRED = "EXPIRED", "Expired"

    TRANSITIONS = {
        Status.PENDING: {Status.ACCEPTED, Status.CANCELLED, Status.EXPIRED},
        Status.ACCEPTED: {Status.PREPARING, Status.CANCELLED},
        Status.PREPARING: {Status.READY, Status.CANCELLED},
        Status.READY: {Status.PICKED_UP, Status.CANCELLED},
        Status.PICKED_UP: {Status.DELIVERED, Status.CANCELLED},
        Status.DELIVERED: set(),
        Status.CANCELLED: set(),
        Status.EXPIRED: set(),
    }

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="orders",
    )

    restaurant = models.ForeignKey(
        Restaurant,
        on_delete=models.PROTECT,
        related_name="orders",
    )

    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.PENDING,
    )

    total_price = models.DecimalField(
        default=0,
        max_digits=10,
        decimal_places=2,
    )

    delivery_address = models.TextField()

    delivery_location = models.PointField(
        geography=True,
        blank=True,
        null=True,
    )

    accepted_at = models.DateTimeField(blank=True, null=True)
    preparing_at = models.DateTimeField(blank=True, null=True)
    ready_at = models.DateTimeField(blank=True, null=True)
    picked_up_at = models.DateTimeField(blank=True, null=True)
    delivered_at = models.DateTimeField(blank=True, null=True)
    cancelled_at = models.DateTimeField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        super().clean()
        if self.pk:
            old = Order.objects.get(pk=self.pk)
            if old.status != self.status and self.status not in self.TRANSITIONS.get(
                old.status, set()
            ):
                raise ValidationError(
                    f"Cannot transition order from {old.status} to {self.status}."
                )

    def save(self, *args, **kwargs):
        from django.utils import timezone

        is_transition = False
        if self.pk:
            old = Order.objects.get(pk=self.pk)
            is_transition = old.status != self.status
            if is_transition and self.status not in self.TRANSITIONS.get(
                old.status, set()
            ):
                raise ValidationError(
                    f"Cannot transition order from {old.status} to {self.status}."
                )

            if is_transition and not getattr(self, "_skip_timestamp", False):
                now = timezone.now()
                if self.status == Order.Status.ACCEPTED and not self.accepted_at:
                    self.accepted_at = now
                elif self.status == Order.Status.PREPARING and not self.preparing_at:
                    self.preparing_at = now
                elif self.status == Order.Status.READY and not self.ready_at:
                    self.ready_at = now
                elif self.status == Order.Status.PICKED_UP and not self.picked_up_at:
                    self.picked_up_at = now
                elif self.status == Order.Status.DELIVERED and not self.delivered_at:
                    self.delivered_at = now
                elif self.status == Order.Status.CANCELLED and not self.cancelled_at:
                    self.cancelled_at = now

        super().save(*args, **kwargs)


class OrderItem(models.Model):
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="items",
    )

    menu_item = models.ForeignKey(
        MenuItem,
        on_delete=models.PROTECT,
        related_name="order_items",
    )

    quantity = models.PositiveIntegerField()

    price_snapshot = models.DecimalField(
        max_digits=10,
        decimal_places=2,
    )

    created_at = models.DateTimeField(auto_now_add=True)
