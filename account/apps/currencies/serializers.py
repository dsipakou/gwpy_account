from currencies.models import Currency
from rest_framework import serializers


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
        if value:
            Currency.objects.filter(is_base=True).update(is_base=False)
        return value

    def validate_is_default(self, value):
        if value:
            Currency.objects.filter(is_default=True).update(is_default=False)
        return value
