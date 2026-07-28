from decimal import Decimal

from rest_framework import serializers

from config.fields import LocationField
from restaurants.models import Restaurant

from .models import Cart, CartItem, Order, OrderItem


class CartItemSerializer(serializers.ModelSerializer):
    menu_item_name = serializers.CharField(source="menu_item.name", read_only=True)
    price = serializers.DecimalField(
        source="menu_item.price", max_digits=10, decimal_places=2, read_only=True
    )

    class Meta:
        model = CartItem
        fields = (
            "id",
            "menu_item",
            "menu_item_name",
            "quantity",
            "price_snapshot",
            "price",
            "created_at",
        )
        read_only_fields = ("price_snapshot", "created_at")


class CartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True, read_only=True)
    total = serializers.SerializerMethodField()

    class Meta:
        model = Cart
        fields = ("id", "items", "total", "created_at", "updated_at")
        read_only_fields = ("created_at", "updated_at")

    def get_total(self, obj):
        return sum(
            (item.price_snapshot * item.quantity for item in obj.items.all()),
            Decimal(0),
        )


class OrderItemSerializer(serializers.ModelSerializer):
    menu_item_name = serializers.CharField(source="menu_item.name", read_only=True)

    class Meta:
        model = OrderItem
        fields = (
            "id",
            "menu_item",
            "menu_item_name",
            "quantity",
            "price_snapshot",
            "created_at",
        )
        read_only_fields = ("price_snapshot", "created_at")


class CheckoutSerializer(serializers.Serializer):
    restaurant = serializers.PrimaryKeyRelatedField(queryset=Restaurant.objects.all())
    delivery_address = serializers.CharField(max_length=500)
    delivery_location = LocationField(required=False)


class OrderSerializer(serializers.ModelSerializer):
    restaurant_name = serializers.CharField(source="restaurant.name", read_only=True)
    items = OrderItemSerializer(many=True, read_only=True)
    delivery_location = LocationField(required=False)
    customer = serializers.PrimaryKeyRelatedField(source="user", read_only=True)

    class Meta:
        model = Order
        fields = (
            "id",
            "customer",
            "restaurant",
            "restaurant_name",
            "status",
            "total_price",
            "delivery_address",
            "delivery_location",
            "items",
            "accepted_at",
            "preparing_at",
            "ready_at",
            "picked_up_at",
            "delivered_at",
            "cancelled_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "status",
            "total_price",
            "accepted_at",
            "preparing_at",
            "ready_at",
            "picked_up_at",
            "delivered_at",
            "cancelled_at",
            "created_at",
            "updated_at",
        )
