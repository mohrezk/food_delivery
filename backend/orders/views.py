from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import OpenApiResponse, extend_schema

from accounts.models import User
from accounts.serializers import UserSerializer
from restaurants.models import MenuItem

from payments.services import get_payment_service

from chat.services import get_or_create_conversation_for_order
from config.events import publish_group
from notifications.tasks import (
    notify_driver_assigned,
    notify_order_status_change,
)

from .models import Cart, CartItem, Order, OrderItem
from .serializers import (
    CartItemSerializer,
    CartSerializer,
    CheckoutSerializer,
    DriverLocationUpdateSerializer,
    OrderSerializer,
    VendorOrderStatusUpdateSerializer,
)


def publish_order_status(order):
    publish_group(
        f"order_{order.id}",
        {"type": "order.status", "order": OrderSerializer(order).data},
    )


class CartView(APIView):
    serializer_class = CartSerializer
    permission_classes = (IsAuthenticated,)

    def _get_or_create_cart(self):
        cart, _ = Cart.objects.get_or_create(user=self.request.user)
        return cart

    def get(self, request):
        cart = self._get_or_create_cart()
        serializer = CartSerializer(cart)
        return Response(serializer.data)


class CartItemViewSet(viewsets.ModelViewSet):
    serializer_class = CartItemSerializer
    queryset = CartItem.objects.all()
    permission_classes = (IsAuthenticated,)

    def get_queryset(self):
        return CartItem.objects.select_related(
            "cart",
            "menu_item",
            "cart__user",
        ).filter(cart__user=self.request.user)

    def create(self, request, *args, **kwargs):
        cart, _ = Cart.objects.get_or_create(user=request.user)
        menu_item_id = request.data.get("menu_item")
        quantity = int(request.data.get("quantity", 1))

        if quantity < 1:
            raise ValidationError({"quantity": "Must be >= 1."})

        try:
            menu_item = MenuItem.objects.get(pk=menu_item_id)
        except (MenuItem.DoesNotExist, ValueError, TypeError):
            raise ValidationError({"menu_item": "Invalid menu item."})

        if not menu_item.is_available:
            raise ValidationError({"menu_item": "Item not available."})

        existing = CartItem.objects.filter(cart=cart, menu_item=menu_item).first()
        if existing:
            existing.quantity += quantity
            existing.price_snapshot = menu_item.price
            existing.save()
            item, created = existing, False
        else:
            item = CartItem.objects.create(
                cart=cart,
                menu_item=menu_item,
                quantity=quantity,
                price_snapshot=menu_item.price,
            )
            created = True

        cart.save(update_fields=["updated_at"])
        serializer = self.get_serializer(item)
        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)

        new_qty = serializer.validated_data.get("quantity")
        if new_qty is not None and new_qty < 1:
            raise ValidationError({"quantity": "Must be >= 1."})

        for attr, value in serializer.validated_data.items():
            setattr(instance, attr, value)
        if "menu_item" in serializer.validated_data:
            instance.price_snapshot = serializer.validated_data["menu_item"].price
        instance.save()
        instance.cart.save(update_fields=["updated_at"])
        return Response(self.get_serializer(instance).data)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.delete()
        cart = instance.cart
        cart.save(update_fields=["updated_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class CheckoutView(APIView):
    permission_classes = (IsAuthenticated,)

    @transaction.atomic
    @extend_schema(
        request=CheckoutSerializer,
        responses={201: OrderSerializer, 400: OpenApiResponse(description="Invalid checkout request")},
    )
    def post(self, request):
        serializer = CheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        restaurant = data["restaurant"]
        cart, _ = Cart.objects.get_or_create(user=request.user)

        cart_items = list(cart.items.select_related("menu_item"))
        if not cart_items:
            raise ValidationError({"cart": "Cart is empty."})

        cross_restaurant = [
            ci.menu_item.restaurant_id
            for ci in cart_items
            if ci.menu_item.restaurant_id != restaurant.id
        ]
        if cross_restaurant:
            raise ValidationError(
                {"cart": "All cart items must belong to the selected restaurant."}
            )

        order = Order.objects.create(
            user=request.user,
            restaurant=restaurant,
            delivery_address=data["delivery_address"],
            delivery_location=data.get("delivery_location"),
            status=Order.Status.PENDING,
        )

        total = Decimal(0)
        for ci in cart_items:
            line_total = ci.price_snapshot * ci.quantity
            total += line_total
            OrderItem.objects.create(
                order=order,
                menu_item=ci.menu_item,
                quantity=ci.quantity,
                price_snapshot=ci.price_snapshot,
            )

        order.total_price = total
        order.save(update_fields=["total_price"])

        get_payment_service().create_payment(order)

        cart.items.all().delete()

        notify_order_status_change.delay(order.id)
        publish_order_status(order)
        publish_group(
            f"vendor_{order.restaurant.owner_id}",
            {"type": "order.new", "order": OrderSerializer(order).data},
        )

        return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED)


class OrderViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = OrderSerializer
    queryset = Order.objects.all()
    permission_classes = (IsAuthenticated,)

    def get_queryset(self):
        return (
            Order.objects.filter(user=self.request.user)
            .select_related("restaurant")
            .prefetch_related("items", "items__menu_item")
            .order_by("-created_at")
        )


class CancelOrderView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        request=None,
        responses={200: OrderSerializer, 400: OpenApiResponse(description="Order cannot be cancelled")},
    )
    def post(self, request, pk):
        order = get_object_or_404(Order, pk=pk, user=request.user)

        if order.status != Order.Status.PENDING:
            raise ValidationError(
                {"status": f"Cannot cancel order in status {order.status}."}
            )

        order.status = Order.Status.CANCELLED
        try:
            order.save()
        except DjangoValidationError as e:
            raise ValidationError(
                e.message_dict if hasattr(e, "message_dict") else e.messages
            )

        notify_order_status_change.delay(order.id)
        publish_order_status(order)

        return Response(OrderSerializer(order).data, status=status.HTTP_200_OK)


class VendorOrderListView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(responses={200: OrderSerializer(many=True)})
    def get(self, request):
        if request.user.role != User.Role.VENDOR:
            raise PermissionDenied("Only vendors can access this endpoint.")

        orders = (
            Order.objects.filter(restaurant__owner=request.user)
            .select_related("restaurant", "user", "driver")
            .prefetch_related("items", "items__menu_item")
            .order_by("-created_at")
        )
        return Response(OrderSerializer(orders, many=True).data)


class VendorOrderStatusUpdateView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        request=VendorOrderStatusUpdateSerializer,
        responses={200: OrderSerializer, 400: OpenApiResponse(description="Invalid transition")},
    )
    def post(self, request, pk):
        if request.user.role != User.Role.VENDOR:
            raise PermissionDenied("Only vendors can update order status.")

        order = get_object_or_404(Order, pk=pk, restaurant__owner=request.user)
        serializer = VendorOrderStatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        order.status = serializer.validated_data["status"]
        try:
            order.save()
        except DjangoValidationError as e:
            raise ValidationError(
                e.message_dict if hasattr(e, "message_dict") else e.messages
            )

        notify_order_status_change.delay(order.id)
        publish_order_status(order)

        return Response(OrderSerializer(order).data, status=status.HTTP_200_OK)


class DriverAvailableOrdersView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(responses={200: OrderSerializer(many=True)})
    def get(self, request):
        if request.user.role != User.Role.DRIVER:
            raise PermissionDenied("Only drivers can access this endpoint.")

        orders = (
            Order.objects.filter(status=Order.Status.READY, driver__isnull=True)
            .select_related("restaurant", "user")
            .prefetch_related("items", "items__menu_item")
            .order_by("-created_at")
        )
        return Response(OrderSerializer(orders, many=True).data)


class DriverClaimOrderView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(request=None, responses={200: OrderSerializer})
    def post(self, request, pk):
        if request.user.role != User.Role.DRIVER:
            raise PermissionDenied("Only drivers can claim orders.")

        order = get_object_or_404(Order, pk=pk)

        if order.status != Order.Status.READY:
            raise ValidationError({"status": "Only READY orders can be claimed."})
        if order.driver and order.driver != request.user:
            raise ValidationError({"driver": "Order is already claimed by another driver."})

        order.driver = request.user
        order.save(update_fields=["driver", "updated_at"])

        get_or_create_conversation_for_order(order)
        notify_driver_assigned.delay(order.id)
        publish_order_status(order)

        return Response(OrderSerializer(order).data, status=status.HTTP_200_OK)


class DriverPickedUpOrderView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(request=None, responses={200: OrderSerializer})
    def post(self, request, pk):
        if request.user.role != User.Role.DRIVER:
            raise PermissionDenied("Only drivers can pick up orders.")

        order = get_object_or_404(Order, pk=pk, driver=request.user)

        if order.status != Order.Status.READY:
            raise ValidationError({"status": "Order must be READY before pickup."})

        order.status = Order.Status.PICKED_UP
        try:
            order.save()
        except DjangoValidationError as e:
            raise ValidationError(
                e.message_dict if hasattr(e, "message_dict") else e.messages
            )

        notify_order_status_change.delay(order.id)
        publish_order_status(order)

        return Response(OrderSerializer(order).data, status=status.HTTP_200_OK)


class DriverDeliveredOrderView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(request=None, responses={200: OrderSerializer})
    def post(self, request, pk):
        if request.user.role != User.Role.DRIVER:
            raise PermissionDenied("Only drivers can deliver orders.")

        order = get_object_or_404(Order, pk=pk, driver=request.user)

        if order.status != Order.Status.PICKED_UP:
            raise ValidationError({"status": "Order must be PICKED_UP before delivery."})

        order.status = Order.Status.DELIVERED
        try:
            order.save()
        except DjangoValidationError as e:
            raise ValidationError(
                e.message_dict if hasattr(e, "message_dict") else e.messages
            )

        notify_order_status_change.delay(order.id)
        publish_order_status(order)

        return Response(OrderSerializer(order).data, status=status.HTTP_200_OK)


class DriverLocationUpdateView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        request=DriverLocationUpdateSerializer,
        responses={200: UserSerializer},
    )
    def patch(self, request):
        if request.user.role != User.Role.DRIVER:
            raise PermissionDenied("Only drivers can update their location.")

        serializer = DriverLocationUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        request.user.location = data["location"]
        if "is_available" in data:
            request.user.is_available = data["is_available"]
        request.user.save(update_fields=["location", "is_available"])

        location = data["location"]
        active_orders = Order.objects.filter(
            driver=request.user,
            status__in=[Order.Status.READY, Order.Status.PICKED_UP],
        )
        for order in active_orders:
            publish_group(
                f"order_{order.id}",
                {
                    "type": "order.location",
                    "order_id": order.id,
                    "location": {"lat": location.y, "lng": location.x},
                },
            )

        return Response(UserSerializer(request.user).data, status=status.HTTP_200_OK)


class DriverOrderListView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(responses={200: OrderSerializer(many=True)})
    def get(self, request):
        if request.user.role != User.Role.DRIVER:
            raise PermissionDenied("Only drivers can access this endpoint.")

        orders = (
            Order.objects.filter(driver=request.user)
            .select_related("restaurant", "user", "driver")
            .prefetch_related("items", "items__menu_item")
            .order_by("-created_at")
        )
        return Response(OrderSerializer(orders, many=True).data)


class DriverOrderDetailView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(responses={200: OrderSerializer, 404: OpenApiResponse(description="Order not found")})
    def get(self, request, pk):
        if request.user.role != User.Role.DRIVER:
            raise PermissionDenied("Only drivers can access this endpoint.")

        order = get_object_or_404(Order, pk=pk, driver=request.user)
        return Response(OrderSerializer(order).data)
