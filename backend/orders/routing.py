from django.urls import path

from .consumers import OrderConsumer, VendorOrdersConsumer

websocket_urlpatterns = [
    path("ws/orders/<int:order_id>/", OrderConsumer.as_asgi()),
    path("ws/vendor/orders/", VendorOrdersConsumer.as_asgi()),
]
