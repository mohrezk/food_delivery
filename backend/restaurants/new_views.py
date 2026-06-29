from rest_framework import viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny

from .models import Restaurant, MenuItem
from .serializers import (
    RestaurantSerializer,
    RestaurantDetailSerializer,
    MenuItemSerializer,
    MenuItemWriteSerializer,
)

from accounts.permissions import IsRestaurantOwner, IsVendor, IsMenuItemOwner


class RestaurantViewSet(viewsets.ModelViewSet):

    def get_queryset(self):
        queryset = Restaurant.objects.all()

        if self.action == "retrieve":
            queryset = queryset.prefetch_related("menu_items")

        return queryset

    def get_serializer_class(self):
        if self.action == "retrieve":
            return RestaurantDetailSerializer

        return RestaurantSerializer

    def get_permissions(self):
        if self.action in (
            "update",
            "partial_update",
            "destroy",
        ):
            return [IsRestaurantOwner()]
        elif self.action == "create":
            return [IsVendor()]
        return [AllowAny()]

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)


class MenuItemViewSet(viewsets.ModelViewSet):

    def get_queryset(self):
        return MenuItem.objects.select_related("restaurant")

    def perform_create(self, serializer):
        restaurant = serializer.validated_data["restaurant"]

        if restaurant.owner != self.request.user:
            raise PermissionDenied("You don't own this restaurant.")

        serializer.save()

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return MenuItemWriteSerializer

        return MenuItemSerializer

    def get_permissions(self):
        if self.action == "create":
            return [IsVendor()]

        if self.action in (
            "update",
            "partial_update",
            "destroy",
        ):
            return [IsMenuItemOwner()]

        return [AllowAny()]