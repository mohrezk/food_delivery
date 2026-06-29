from rest_framework.permissions import BasePermission
from accounts.models import User


class IsVendor(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == User.Role.VENDOR


class IsRestaurantOwner(BasePermission):
    def has_object_permission(self, request, view, obj):
        return (
            request.user.is_authenticated
            and request.user.role == "VENDOR"
            and obj.owner == request.user
        )
    

class IsMenuItemOwner(BasePermission):

    def has_object_permission(self, request, view, obj):
        return (
            request.user.is_authenticated
            and obj.restaurant.owner == request.user
        )