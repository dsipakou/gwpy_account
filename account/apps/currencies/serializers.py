from rest_framework import serializers

from currencies.models import Currency


class CurrencySerializer(serializers.ModelSerializer):
    class Meta:
        model = Currency
        fields = (
            "uuid",
            "code",
            "sign",
            "verbal_name",
            "comments",
            "is_base",
            "is_default",
            "created_at",
            "modified_at",
        )

    def validate_is_base(self, value):
        user = self.context["request"].user
        if value:
            Currency.objects.filter(
                is_base=True, workspace=user.active_workspace
            ).update(is_base=False)
        return value

    def validate_is_default(self, value):
        user = self.context["request"].user
        if value:
            Currency.objects.filter(
                is_default=True, workspace=user.active_workspace
            ).update(is_default=False)
        return value

    def create(self, validated_data):
        user = self.context["request"].user
        is_base_currency_exists = Currency.objects.filter(
            is_base=True, workspace=user.active_workspace
        ).exists()
        if not is_base_currency_exists:
            validated_data["is_base"] = True

        currency = Currency.objects.create(
            workspace=user.active_workspace,
            **validated_data,
        )

        if validated_data.get("is_base"):
            user.default_currency = currency
            user.save(force_update=True, update_fields=("default_currency",))

        return currency
