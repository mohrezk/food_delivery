import random

from django.conf import settings

from .models import Payment


class MockPaymentService:
    def create_payment(self, order):
        succeeded = random.random() < 0.9
        status = Payment.Status.SUCCEEDED if succeeded else Payment.Status.FAILED
        payment = Payment.objects.create(
            order=order,
            amount=order.total_price,
            status=status,
            method="mock",
            gateway_response={
                "provider": "mock",
                "success": succeeded,
                "transaction_id": f"mock_{order.id}",
            },
        )
        return payment

    def capture_payment(self, payment):
        if payment.status == Payment.Status.SUCCEEDED:
            return payment
        payment.status = Payment.Status.SUCCEEDED
        payment.gateway_response["captured"] = True
        payment.save(update_fields=["status", "gateway_response", "updated_at"])
        return payment

    def refund_payment(self, payment):
        if payment.status == Payment.Status.REFUNDED:
            return payment
        payment.status = Payment.Status.REFUNDED
        payment.gateway_response["refunded"] = True
        payment.save(update_fields=["status", "gateway_response", "updated_at"])
        return payment


def get_payment_service():
    service_path = getattr(settings, "PAYMENT_SERVICE", "payments.services.MockPaymentService")
    module_path, class_name = service_path.rsplit(".", 1)
    module = __import__(module_path, fromlist=[class_name])
    return getattr(module, class_name)()
