from celery import shared_task

from config.events import publish_group
from orders.models import Order
from orders.utils import order_display_code

from .models import Notification


def _broadcast_notifications(notifications):
    for notification in notifications:
        publish_group(
            f"user_{notification.user_id}",
            {
                "type": "notification.created",
                "notification": {
                    "id": notification.id,
                    "type": notification.type,
                    "title": notification.title,
                    "message": notification.message,
                    "order_id": notification.order_id,
                    "is_read": notification.is_read,
                    "created_at": (
                        notification.created_at.isoformat()
                        if notification.created_at
                        else None
                    ),
                },
            },
        )


@shared_task
def notify_order_status_change(order_id):
    try:
        order = (
            Order.objects.select_related(
                "restaurant", "restaurant__owner", "user", "driver"
            )
            .get(pk=order_id)
        )
    except Order.DoesNotExist:
        return {"notified": 0}

    restaurant_name = order.restaurant.name
    notifications = []

    def add(user, title, message):
        if user:
            notifications.append(
                Notification(
                    user=user,
                    type=Notification.Type.ORDER,
                    title=title,
                    message=message,
                    order=order,
                )
            )

    if order.status == Order.Status.PENDING:
        add(
            order.restaurant.owner,
            "New order",
            f"New order #{order_display_code(order)} at {restaurant_name} has been placed.",
        )
    elif order.status == Order.Status.ACCEPTED:
        add(
            order.user,
            "Order accepted",
            f"Your order at {restaurant_name} has been accepted.",
        )
    elif order.status == Order.Status.PREPARING:
        add(
            order.user,
            "Order being prepared",
            f"Your order at {restaurant_name} is being prepared.",
        )
    elif order.status == Order.Status.READY:
        add(
            order.user,
            "Order ready",
            f"Your order at {restaurant_name} is ready for pickup.",
        )
        add(
            order.driver,
            "Order ready for pickup",
            f"Order #{order_display_code(order)} at {restaurant_name} is ready for pickup.",
        )
    elif order.status == Order.Status.PICKED_UP:
        add(
            order.user,
            "Order on the way",
            f"Your order at {restaurant_name} has been picked up and is on its way.",
        )
        add(
            order.restaurant.owner,
            "Order picked up",
            f"Order #{order_display_code(order)} has been picked up by the driver.",
        )
    elif order.status == Order.Status.DELIVERED:
        add(
            order.user,
            "Order delivered",
            f"Your order at {restaurant_name} has been delivered. Enjoy!",
        )
        add(
            order.restaurant.owner,
            "Order delivered",
            f"Order #{order_display_code(order)} has been delivered.",
        )
    elif order.status == Order.Status.CANCELLED:
        add(
            order.restaurant.owner,
            "Order cancelled",
            f"Order #{order_display_code(order)} was cancelled by the customer.",
        )
        add(
            order.driver,
            "Order cancelled",
            f"Order #{order_display_code(order)} assigned to you was cancelled.",
        )

    if notifications:
        Notification.objects.bulk_create(notifications)
        _broadcast_notifications(notifications)

    return {"notified": len(notifications)}


@shared_task
def notify_driver_assigned(order_id):
    try:
        order = (
            Order.objects.select_related("restaurant__owner", "user", "driver")
            .get(pk=order_id)
        )
    except Order.DoesNotExist:
        return {"notified": 0}

    if not order.driver:
        return {"notified": 0}

    notifications = [
        Notification(
            user=recipient,
            type=Notification.Type.ORDER,
            title="Driver assigned",
            message=f"A driver has been assigned to order #{order_display_code(order)}.",
            order=order,
        )
        for recipient in (order.user, order.restaurant.owner)
        if recipient
    ]

    if notifications:
        Notification.objects.bulk_create(notifications)
        _broadcast_notifications(notifications)

    return {"notified": len(notifications)}


@shared_task
def notify_new_chat_message(message_id):
    from chat.models import Message

    try:
        message = (
            Message.objects.select_related("conversation", "sender")
            .get(pk=message_id)
        )
    except Message.DoesNotExist:
        return {"notified": 0}

    conversation = message.conversation
    recipients = conversation.participants.exclude(pk=message.sender_id)

    notifications = [
        Notification(
            user=recipient,
            type=Notification.Type.CHAT,
            title=f"New message from {message.sender.username}",
            message=f"Order #{order_display_code(conversation.order)}: {message.body[:140]}",
            order=conversation.order,
        )
        for recipient in recipients
    ]

    if notifications:
        Notification.objects.bulk_create(notifications)
        _broadcast_notifications(notifications)

    return {"notified": len(notifications)}
