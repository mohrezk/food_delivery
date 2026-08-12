from channels.generic.websocket import AsyncJsonWebsocketConsumer

from config.db_sync import database_sync_to_async


def _is_participant(user_id, conversation_id):
    from .models import Conversation

    return (
        Conversation.objects.filter(
            id=conversation_id, participants__id=user_id
        ).exists()
    )


class ChatConsumer(AsyncJsonWebsocketConsumer):
    """Receive-only: real-time delivery of chat messages.

    Messages are sent via the REST endpoint, which publishes to the
    conversation group; this consumer just relays them to connected clients.
    """

    async def connect(self):
        user = self.scope["user"]
        conversation_id = self.scope["url_route"]["kwargs"]["conversation_id"]

        if not user.is_authenticated:
            await self.close()
            return

        is_participant = await database_sync_to_async(_is_participant)(
            user.id, conversation_id
        )
        if not is_participant:
            await self.close()
            return

        self.group_name = f"chat_{conversation_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def message_created(self, event):
        await self.send_json(
            {"type": "message.created", "message": event["message"]}
        )
