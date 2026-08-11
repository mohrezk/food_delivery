from .models import Conversation


def get_or_create_conversation_for_order(order):
    """Get (or create) the order conversation with all parties included."""
    conversation, created = Conversation.objects.get_or_create(order=order)
    if created:
        conversation.participants.set([order.user, order.restaurant.owner, order.driver])
    return conversation, created
