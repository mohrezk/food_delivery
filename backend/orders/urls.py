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
    path("", include(router.urls)),
]
