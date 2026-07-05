from django.urls import include, path
from rest_framework.routers import DefaultRouter

# from . import views

from . import views

router = DefaultRouter()
router.register(r'restaurants', views.RestaurantViewSet, basename='restaurant')
router.register(r'menu-items', views.MenuItemViewSet, basename='item')

urlpatterns = [
    path('', include(router.urls)),
]


