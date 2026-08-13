import base64
import hashlib

from django.conf import settings


def order_display_code(order) -> str:
    """Build a stable, non-sequential display reference for an order.

    The code is a keyed hash of the order's own data (id, creation time,
    customer and total) rather than a raw database id, so the sequential
    primary key is never exposed to customers, vendors or drivers. It is
    deterministic: the same order always yields the same code.
    """
    key = settings.SECRET_KEY.encode()
    raw = (
        f"{order.id}|{order.created_at.isoformat()}|"
        f"{order.user_id}|{order.total_price}"
    ).encode()
    digest = hashlib.blake2b(raw, key=key, digest_size=5).digest()
    code = base64.b32encode(digest).decode("ascii").rstrip("=")
    return f"FD-{code}"