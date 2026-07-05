from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from .models import Cart, CartItem, Order, OrderItem

from .serializers import (
    CartSerializer,
    CartItemSerializer,
    OrderSerializer,
    OrderItemSerializer,
)


class CartViewSet(viewsets.ModelViewSet):
    serializer_class = CartSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Cart.objects.filter(user=self.request.user).prefetch_related(
            "items",
            "items__menu_item",
        )

    def perform_create(self, serializer):
        serializer.save(
            user=self.request.user,
        )


class CartItemViewSet(viewsets.ModelViewSet):
    serializer_class = CartItemSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return CartItem.objects.select_related(
            "cart",
            "menu_item",
        ).filter(
            cart__user=self.request.user,
        )

    def perform_create(self, serializer):
        cart = serializer.validated_data["cart"]

        if cart.user != self.request.user:
            raise PermissionError("You cannot add items to another user's cart.")

        serializer.save(price_snapshot=serializer.validated_data["menu_item"].price)


class OrderViewSet(viewsets.ModelViewSet):
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (
            Order.objects.filter(user=self.request.user)
            .select_related(
                "restaurant",
            )
            .prefetch_related(
                "items",
                "items__menu_item",
            )
        )

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
