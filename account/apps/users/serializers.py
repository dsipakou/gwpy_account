from rest_framework import serializers
from users.models import User


class UserSerializer(serializers.ModelSerializer):
    currency = serializers.CharField(source="currency_code")

    class Meta:
        model = User
        fields = (
            "uuid",
            "username",
            "email",
            "currency",
            "first_name",
            "last_name",
            "is_staff",
            "is_active",
            "date_joined",
        )


class UserLoginSerializer(serializers.Serializer):
    email = serializers.CharField()
    password = serializers.CharField()


class ChangeDefaultCurrencySerializer(serializers.Serializer):
    currency = serializers.CharField()
