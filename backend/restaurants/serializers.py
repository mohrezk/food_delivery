from rest_framework import serializers
from config.fields import LocationField
from .models import Restaurant, MenuItem


class MenuItemSerializer(serializers.ModelSerializer):
    restaurant_name = serializers.CharField(
        source="restaurant.name",
        read_only=True,
    )

    class Meta:
        model = MenuItem
        fields = (
            "id",
            "restaurant",
            "restaurant_name",
            "name",
            "description",
            "price",
            "image",
            "is_available",
            "created_at",
            "updated_at",
        )


class MenuItemWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = MenuItem
        fields = (
            "id",
            "name",
            "description",
            "price",
            "image",
            "is_available",
            "restaurant",
        )


class RestaurantSerializer(serializers.ModelSerializer):
    location = LocationField(required=False)

    class Meta:
        model = Restaurant
        fields = (
            "id",
            "owner",
            "name",
            "address",
            "location",
            "image",
            "status",
            "created_at",
        )
        read_only_fields = ("owner", "created_at")


class RestaurantDetailSerializer(serializers.ModelSerializer):
    location = LocationField(required=False)
    menu_items = MenuItemSerializer(many=True, read_only=True)

    class Meta:
        model = Restaurant
        fields = (
            "id",
            "owner",
            "name",
            "address",
            "location",
            "image",
            "status",
            "created_at",
            "menu_items",
        )
        read_only_fields = ("owner", "created_at")
