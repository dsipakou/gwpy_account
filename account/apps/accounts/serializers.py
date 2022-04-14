from rest_framework import serializers

from .models import Account


class AccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = Account
        fields = (
            "uuid",
            "user",
            "source",
            "amount",
            "description",
            "is_main",
            "created_at",
            "modified_at",
        )
