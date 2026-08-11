from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Notification
from .serializers import NotificationSerializer


class NotificationListView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(responses={200: NotificationSerializer(many=True)})
    def get(self, request):
        notifications = Notification.objects.filter(user=request.user)
        return Response(NotificationSerializer(notifications, many=True).data)


class NotificationReadView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(request=None, responses={200: NotificationSerializer})
    def post(self, request, pk):
        notification = get_object_or_404(
            Notification, pk=pk, user=request.user
        )
        if not notification.is_read:
            notification.is_read = True
            notification.save(update_fields=["is_read"])
        return Response(
            NotificationSerializer(notification).data, status=status.HTTP_200_OK
        )


class NotificationReadAllView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(request=None, responses={200: OpenApiResponse(description="Marked all read")})
    def post(self, request):
        updated = (
            Notification.objects.filter(user=request.user, is_read=False).update(
                is_read=True
            )
        )
        return Response({"updated": updated}, status=status.HTTP_200_OK)


class NotificationUnreadCountView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(responses={200: OpenApiResponse(description="Unread count")})
    def get(self, request):
        count = Notification.objects.filter(user=request.user, is_read=False).count()
        return Response({"unread_count": count})
