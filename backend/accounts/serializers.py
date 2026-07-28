from rest_framework import serializers
from config.fields import LocationField
from .models import User


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ("email", "username", "password", "phone", "role")

    def validate_role(self, value):
        if value == User.Role.ADMIN:
            raise serializers.ValidationError("Cannot register as admin.")
        return value

    def create(self, validated_data):
        password = validated_data.pop("password")
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user


class UserSerializer(serializers.ModelSerializer):
    location = LocationField(required=False)

    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "username",
            "phone",
            "role",
            "location",
            "is_available",
            "avg_rating",
            "rating_count",
        )
