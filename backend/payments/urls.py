from django.urls import path

from . import views

urlpatterns = [
    path("payments/<int:order_id>/", views.PaymentDetailView.as_view(), name="payment-detail"),
]
