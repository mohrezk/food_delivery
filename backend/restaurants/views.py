from rest_framework import viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny

from django.contrib.gis.db.models.functions import Distance
from django.contrib.gis.geos import Point
from django.contrib.gis.measure import D

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

        lat = self.request.query_params.get("lat")
        lng = self.request.query_params.get("lng")
        radius_km = self.request.query_params.get("radius", 5)

        if lat and lng:
            try:
                user_location = Point(float(lng), float(lat), srid=4326)

                queryset = queryset.filter(
                    location__distance_lte=(user_location, D(km=radius_km))
                ).annotate(
                    distance=Distance("location", user_location)
                ).order_by("distance")
            except (ValueError, TypeError):
                pass

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