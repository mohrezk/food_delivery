from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from notifications.tasks import notify_new_chat_message

from config.events import publish_group

from .models import Conversation, Message
from .serializers import (
    ConversationDetailSerializer,
    ConversationListSerializer,
    MessageSerializer,
    SendMessageSerializer,
)


class ConversationListView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(responses={200: ConversationListSerializer(many=True)})
    def get(self, request):
        conversations = (
            Conversation.objects.filter(participants=request.user)
            .prefetch_related("participants", "messages__sender")
            .order_by("-updated_at")
        )
        serializer = ConversationListSerializer(
            conversations, many=True, context={"request": request}
        )
        return Response(serializer.data)


class ConversationDetailView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        responses={
            200: ConversationDetailSerializer,
            404: OpenApiResponse(description="Conversation not found"),
        }
    )
    def get(self, request, pk):
        conversation = get_object_or_404(
            Conversation, pk=pk, participants=request.user
        )
        serializer = ConversationDetailSerializer(
            conversation, context={"request": request}
        )
        return Response(serializer.data)


class SendMessageView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        request=SendMessageSerializer,
        responses={
            201: MessageSerializer,
            404: OpenApiResponse(description="Conversation not found"),
        },
    )
    def post(self, request, pk):
        conversation = get_object_or_404(
            Conversation, pk=pk, participants=request.user
        )
        serializer = SendMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        message = Message.objects.create(
            conversation=conversation,
            sender=request.user,
            body=serializer.validated_data["body"],
        )
        Conversation.objects.filter(pk=conversation.pk).update(
            updated_at=message.created_at
        )
        notify_new_chat_message.delay(message.pk)
        publish_group(
            f"chat_{conversation.pk}",
            {"type": "message.created", "message": MessageSerializer(message).data},
        )

        return Response(MessageSerializer(message).data, status=status.HTTP_201_CREATED)


class MarkConversationReadView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(request=None, responses={200: OpenApiResponse(description="Marked read")})
    def post(self, request, pk):
        conversation = get_object_or_404(
            Conversation, pk=pk, participants=request.user
        )
        updated = (
            conversation.messages.filter(is_read=False)
            .exclude(sender=request.user)
            .update(is_read=True)
        )
        return Response({"updated": updated}, status=status.HTTP_200_OK)


class UnreadCountView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(responses={200: OpenApiResponse(description="Unread message count")})
    def get(self, request):
        conversation_ids = Conversation.objects.filter(
            participants=request.user
        ).values_list("id", flat=True)
        count = (
            Message.objects.filter(
                conversation_id__in=conversation_ids,
                is_read=False,
            )
            .exclude(sender=request.user)
            .count()
        )
        return Response({"unread_count": count})
