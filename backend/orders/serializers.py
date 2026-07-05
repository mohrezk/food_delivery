# serializers.py

from rest_framework import serializers

from .models import (
    Cart,
    CartItem,
    Order,
    OrderItem,
)


class CartItemSerializer(serializers.ModelSerializer):
    menu_item_name = serializers.CharField(
        source="menu_item.name",
        read_only=True,
    )

    class Meta:
        model = CartItem
        fields = (
            "id",
            "cart",
            "menu_item",
            "menu_item_name",
            "quantity",
            "price_snapshot",
            "created_at",
        )
        read_only_fields = (
            "price_snapshot",
            "created_at",
        )


class CartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(
        many=True,
        read_only=True,
    )

    class Meta:
        model = Cart
        fields = (
            "id",
            "user",
            "items",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "user",
            "created_at",
            "updated_at",
        )


class OrderItemSerializer(serializers.ModelSerializer):
    menu_item_name = serializers.CharField(
        source="menu_item.name",
        read_only=True,
    )

    class Meta:
        model = OrderItem
        fields = (
            "id",
            "order",
            "menu_item",
            "menu_item_name",
            "quantity",
            "price_snapshot",
            "created_at",
        )
        read_only_fields = (
            "order",
            "price_snapshot",
            "created_at",
        )


class OrderSerializer(serializers.ModelSerializer):
    restaurant_name = serializers.CharField(
        source="restaurant.name",
        read_only=True,
    )

    items = OrderItemSerializer(
        many=True,
        read_only=False,
    )

    class Meta:
        model = Order
        fields = (
            "id",
            "user",
            "restaurant",
            "restaurant_name",
            "status",
            "total_price",
            "delivery_address",
            "items",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "user",
            "created_at",
            "updated_at",
            "total_price",
        )

    def create(self, validated_data):
        items_data = validated_data.pop("items", [])
        order = Order.objects.create(**validated_data)
        total = 0
        for item_data in items_data:
            menu_item = item_data["menu_item"]
            qty = item_data.get("quantity", 1)
            price = menu_item.price
            total += float(price) * qty
            OrderItem.objects.create(
                order=order,
                menu_item=menu_item,
                quantity=qty,
                price_snapshot=price,
            )
        order.total_price = total
        order.save(update_fields=["total_price"])
        return order
