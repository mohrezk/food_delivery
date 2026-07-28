from django.contrib.gis.geos import Point
from rest_framework import serializers


class LocationField(serializers.Field):
    """Accepts {"lat": float, "lng": float} and outputs same JSON.

    Backing model field must be a PostGIS PointField(geography=True, srid=4326).
    Point is built in (lng, lat) order to match GeoJSON / WKT conventions.
    """

    default_error_messages = {
        "invalid": "Expected {lat: float, lng: float} object.",
        "invalid_coord": "lat/lng must be valid numbers within range.",
        "missing": "Both 'lat' and 'lng' are required.",
    }

    def to_internal_value(self, data):
        if not isinstance(data, dict) or "lat" not in data or "lng" not in data:
            self.fail("invalid")

        try:
            lat = float(data["lat"])
            lng = float(data["lng"])
        except (TypeError, ValueError):
            self.fail("invalid_coord")

        if not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
            self.fail("invalid_coord")

        return Point(lng, lat, srid=4326)

    def to_representation(self, value):
        if value is None:
            return None
        if hasattr(value, "empty") and value.empty:
            return None
        if hasattr(value, "y") and hasattr(value, "x"):
            return {"lat": round(value.y, 7), "lng": round(value.x, 7)}
        return None
