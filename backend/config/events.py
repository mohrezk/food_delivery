from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync


def publish_group(group, payload):
    """Publish a JSON payload to a channel group, ignoring transient errors.

    Broadcasts are best-effort: a Redis outage should never break an order
    save or checkout that happens to trigger a publish.
    """
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return

    try:
        async_to_sync(channel_layer.group_send)(group, payload)
    except Exception:
        pass
