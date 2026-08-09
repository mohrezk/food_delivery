from rest_framework import serializers

from .models import Payment


class PaymentSerializer(serializers.ModelSerializer):
    order_id = serializers.PrimaryKeyRelatedField(source="order", read_only=True)

    class Meta:
        model = Payment
        fields = (
            "id",
            "order_id",
            "amount",
            "status",
            "method",
            "gateway_response",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "amount",
            "status",
            "method",
            "gateway_response",
            "created_at",
            "updated_at",
        )
