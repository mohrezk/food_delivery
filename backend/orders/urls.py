from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register(r"cart-items", views.CartItemViewSet, basename="cart_item")
router.register(r"orders", views.OrderViewSet, basename="order")

urlpatterns = [
    path("cart/", views.CartView.as_view(), name="cart"),
    path("orders/checkout/", views.CheckoutView.as_view(), name="checkout"),
    path(
        "orders/<int:pk>/cancel/",
        views.CancelOrderView.as_view(),
        name="order-cancel",
    ),
    path("vendor/orders/", views.VendorOrderListView.as_view(), name="vendor-orders"),
    path(
        "vendor/orders/<int:pk>/status/",
        views.VendorOrderStatusUpdateView.as_view(),
        name="vendor-order-status",
    ),
    path(
        "driver/orders/",
        views.DriverOrderListView.as_view(),
        name="driver-orders",
    ),
    path(
        "driver/orders/<int:pk>/",
        views.DriverOrderDetailView.as_view(),
        name="driver-order-detail",
    ),
    path(
        "driver/orders/available/",
        views.DriverAvailableOrdersView.as_view(),
        name="driver-orders-available",
    ),
    path(
        "driver/orders/<int:pk>/claim/",
        views.DriverClaimOrderView.as_view(),
        name="driver-order-claim",
    ),
    path(
        "driver/orders/<int:pk>/picked-up/",
        views.DriverPickedUpOrderView.as_view(),
        name="driver-order-picked-up",
    ),
    path(
        "driver/orders/<int:pk>/delivered/",
        views.DriverDeliveredOrderView.as_view(),
        name="driver-order-delivered",
    ),
    path(
        "driver/location/",
        views.DriverLocationUpdateView.as_view(),
        name="driver-location",
    ),
    path("", include(router.urls)),
]
