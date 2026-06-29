from django.urls import include, path
from rest_framework.routers import DefaultRouter

# from . import views

from . import new_views

router = DefaultRouter()
router.register(r'restaurant', new_views.RestaurantViewSet, basename='restaurant')
router.register(r'menu-item', new_views.MenuItemViewSet, basename='item')

urlpatterns = [
    path('', include(router.urls)),
    # path("", views.RestaurantListView.as_view(), name="restaurant-list"),
    # path("<int:pk>/", views.RestaurantDetailView.as_view(), name="restaurant-detail"),
]


