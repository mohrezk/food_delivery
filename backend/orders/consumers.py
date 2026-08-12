from channels.generic.websocket import AsyncJsonWebsocketConsumer

from accounts.models import User
from config.db_sync import database_sync_to_async
from orders.models import Order


def _order_access_user(order_id, user):
    if not user.is_authenticated:
        return False
    try:
        order = Order.objects.select_related("restaurant").get(pk=order_id)
    except Order.DoesNotExist:
        return False
    if user.role == User.Role.VENDOR:
        return order.restaurant.owner_id == user.id
    return order.user_id == user.id or order.driver_id == user.id


class OrderConsumer(AsyncJsonWebsocketConsumer):
    """Live order tracking: status changes and driver location updates.

    Accessible to the order's customer, the restaurant owner, and the
    assigned driver.
    """

    async def connect(self):
        user = self.scope["user"]
        order_id = self.scope["url_route"]["kwargs"]["order_id"]

        allowed = await database_sync_to_async(_order_access_user)(order_id, user)
        if not allowed:
            await self.close()
            return

        self.group_name = f"order_{order_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def order_status(self, event):
        await self.send_json({"type": "order.status", "order": event["order"]})

    async def order_location(self, event):
        await self.send_json(
            {
                "type": "order.location",
                "order_id": event["order_id"],
                "location": event["location"],
            }
        )


class VendorOrdersConsumer(AsyncJsonWebsocketConsumer):
    """New-order alerts for restaurant owners."""

    async def connect(self):
        user = self.scope["user"]
        if not user.is_authenticated or user.role != User.Role.VENDOR:
            await self.close()
            return

        self.group_name = f"vendor_{user.id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def order_new(self, event):
        await self.send_json({"type": "order.new", "order": event["order"]})
