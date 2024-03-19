from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from .models import Account


class AccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = Account
        fields = (
            "uuid",
            "user",
            "title",
            "category",
            "description",
            "is_main",
            "created_at",
            "modified_at",
        )

    def create(self, validated_data):
        workspace = validated_data["user"].active_workspace
        if not workspace:
            raise ValidationError("User has no active workspace")
        data = {
            **validated_data,
            "workspace": workspace,
        }
        return super().create(data)


class AccountReassignSerializer(serializers.Serializer):
    account = serializers.UUIDField()

    def validate(self, attrs):
        account = attrs.get("account")
        if not Account.objects.filter(uuid=account).exists():
            raise serializers.ValidationError("Destinated account does not exists")

        return super().validate(attrs)
