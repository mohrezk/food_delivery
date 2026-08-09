from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import OpenApiResponse, extend_schema

from accounts.models import User
from orders.models import Order

from .models import Payment
from .serializers import PaymentSerializer


class PaymentDetailView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(responses={200: PaymentSerializer, 404: OpenApiResponse(description="Payment not found")})
    def get(self, request, order_id):
        order = get_object_or_404(Order, pk=order_id)
        if order.user != request.user and request.user.role != User.Role.ADMIN:
            raise PermissionDenied("You do not have permission to view this payment.")
        payment = get_object_or_404(Payment, order=order)
        serializer = PaymentSerializer(payment)
        return Response(serializer.data)
