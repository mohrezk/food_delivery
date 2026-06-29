# from rest_framework import generics, permissions, status
# from rest_framework.parsers import MultiPartParser, FormParser
# from rest_framework.response import Response
# from django.db.models import Q
# from .models import Restaurant, Category, MenuItem
# from .serializers import (
#     RestaurantSerializer,
#     RestaurantDetailSerializer,
#     CategorySerializer,
#     MenuItemSerializer,
#     MenuItemWriteSerializer,
# )
# from accounts.permissions import IsVendor


# from rest_framework import generics, permissions, status
# from rest_framework import viewsets
# from rest_framework.parsers import MultiPartParser, FormParser
# from rest_framework.response import Response
# from .models import Restaurant, Category, MenuItem
# from .serializers import (
#     RestaurantSerializer,
#     RestaurantDetailSerializer,
#     CategorySerializer,
#     MenuItemSerializer,
#     MenuItemWriteSerializer,
# )
# from accounts.permissions import IsVendor


# class VendorRestaurantView(generics.GenericAPIView):
#     serializer_class = RestaurantSerializer
#     permission_classes = (permissions.IsAuthenticated, IsVendor)
#     parser_classes = (MultiPartParser, FormParser)

#     def get_object(self):
#         return Restaurant.objects.filter(owner=self.request.user).first()

#     def get(self, request, *args, **kwargs):
#         restaurant = self.get_object()
#         if not restaurant:
#             return Response(
#                 {"detail": "No restaurant found. Create one via POST."}, status=404
#             )
#         serializer = self.get_serializer(restaurant)
#         return Response(serializer.data)

#     def post(self, request, *args, **kwargs):
#         if self.get_object():
#             return Response({"detail": "Restaurant already exists."}, status=409)
#         serializer = self.get_serializer(data=request.data)
#         serializer.is_valid(raise_exception=True)
#         serializer.save(owner=request.user)
#         return Response(serializer.data, status=201)

#     def patch(self, request, *args, **kwargs):
#         restaurant = self.get_object()
#         if not restaurant:
#             return Response({"detail": "No restaurant found."}, status=404)
#         serializer = self.get_serializer(restaurant, data=request.data)
#         serializer.is_valid(raise_exception=True)
#         serializer.save()
#         return Response(serializer.data)


# class VendorMenuListView(generics.ListCreateAPIView):
#     serializer_class = MenuItemWriteSerializer
#     permission_classes = (permissions.IsAuthenticated, IsVendor)
#     parser_classes = (MultiPartParser, FormParser)

#     def get_queryset(self):
#         return MenuItem.objects.filter(restaurant__owner=self.request.user)

#     def perform_create(self, serializer):
#         restaurant = Restaurant.objects.get(owner=self.request.user)
#         serializer.save(restaurant=restaurant)


# class VendorMenuDetailView(generics.RetrieveUpdateDestroyAPIView):
#     serializer_class = MenuItemWriteSerializer
#     permission_classes = (permissions.IsAuthenticated, IsVendor)
#     parser_classes = (MultiPartParser, FormParser)

#     def get_queryset(self):
#         return MenuItem.objects.filter(restaurant__owner=self.request.user)


# class VendorCategoryListView(generics.ListCreateAPIView):
#     serializer_class = CategorySerializer
#     permission_classes = (permissions.IsAuthenticated, IsVendor)

#     def get_queryset(self):
#         return Category.objects.filter(restaurant__owner=self.request.user)

#     def perform_create(self, serializer):
#         restaurant = Restaurant.objects.get(owner=self.request.user)
#         serializer.save(restaurant=restaurant)


# class RestaurantListView(generics.ListAPIView):
#     serializer_class = RestaurantSerializer
#     permission_classes = (permissions.AllowAny,)

#     def get_queryset(self):
#         qs = Restaurant.objects.filter(status=Restaurant.Status.OPEN)
#         lat = self.request.query_params.get("lat")
#         lng = self.request.query_params.get("lng")
#         radius = self.request.query_params.get("radius")
#         if lat and lng and radius:
#             try:
#                 lat, lng, radius = float(lat), float(lng), float(radius)
#                 qs = qs.filter(lat__isnull=False, lng__isnull=False)
#                 ids = []
#                 for r in qs:
#                     from math import radians, sin, cos, sqrt, asin

#                     dlat = radians(r.lat - lat)
#                     dlng = radians(r.lng - lng)
#                     a = (
#                         sin(dlat / 2) ** 2
#                         + cos(radians(lat)) * cos(radians(r.lat)) * sin(dlng / 2) ** 2
#                     )
#                     c = 2 * asin(sqrt(a))
#                     if 6371 * c <= radius:
#                         ids.append(r.id)
#                 qs = qs.filter(id__in=ids)
#             except ValueError:
#                 pass
#         return qs


# class RestaurantDetailView(generics.RetrieveAPIView):
#     queryset = Restaurant.objects.all()
#     serializer_class = RestaurantDetailSerializer
#     permission_classes = (permissions.AllowAny,)
