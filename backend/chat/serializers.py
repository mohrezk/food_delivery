from rest_framework import serializers

from accounts.models import User

from .models import Conversation, Message


class ParticipantSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "username", "role")


class MessageSerializer(serializers.ModelSerializer):
    sender = ParticipantSerializer(read_only=True)

    class Meta:
        model = Message
        fields = ("id", "sender", "body", "is_read", "created_at")
        read_only_fields = ("is_read", "created_at")


class SendMessageSerializer(serializers.Serializer):
    body = serializers.CharField(min_length=1, max_length=2000)


class ConversationListSerializer(serializers.ModelSerializer):
    participants = ParticipantSerializer(many=True, read_only=True)
    last_message = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()
    order_id = serializers.IntegerField(read_only=True)
    restaurant_name = serializers.CharField(
        source="order.restaurant.name", read_only=True
    )

    class Meta:
        model = Conversation
        fields = (
            "id",
            "order_id",
            "restaurant_name",
            "participants",
            "last_message",
            "unread_count",
            "created_at",
            "updated_at",
        )

    def get_last_message(self, obj):
        message = obj.messages.select_related("sender").order_by("-created_at").first()
        if message is None:
            return None
        return {
            "id": message.id,
            "sender_id": message.sender_id,
            "sender_username": message.sender.username,
            "body": message.body,
            "created_at": message.created_at,
        }

    def get_unread_count(self, obj):
        user = self.context["request"].user
        return obj.messages.filter(is_read=False).exclude(sender=user).count()


class ConversationDetailSerializer(ConversationListSerializer):
    messages = MessageSerializer(many=True, read_only=True)

    class Meta(ConversationListSerializer.Meta):
        fields = ConversationListSerializer.Meta.fields + ("messages",)
