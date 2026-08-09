from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from .models import Cart

DEFAULT_STALE_HOURS = 24


@shared_task
def refresh_stale_carts(hours=DEFAULT_STALE_HOURS):
    """Non-destructively refresh stale carts.

    For each cart not touched in `hours`:
    - update price snapshots to current menu item prices
    - remove cart items whose menu item is no longer available
    - leave the cart otherwise untouched, and mark it as refreshed
    """
    threshold = timezone.now() - timedelta(hours=hours)
    stale_carts = Cart.objects.filter(updated_at__lt=threshold).prefetch_related(
        "items", "items__menu_item"
    )

    refreshed = 0
    for cart in stale_carts:
        changed = False
        for item in cart.items.all():
            menu_item = item.menu_item
            if not menu_item.is_available:
                item.delete()
                changed = True
            elif item.price_snapshot != menu_item.price:
                item.price_snapshot = menu_item.price
                item.save(update_fields=["price_snapshot"])
                changed = True
        if changed:
            refreshed += 1
        Cart.objects.filter(pk=cart.pk).update(updated_at=timezone.now())

    return {"refreshed_carts": refreshed}
