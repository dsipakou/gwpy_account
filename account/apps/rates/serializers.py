from rates.models import Rate
from rest_framework import serializers


class RateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Rate
        fields = (
            "uuid",
            "currency",
            "base_currency",
            "rate_date",
            "rate",
            "description",
            "created_at",
            "modified_at",
        )


class RateChartDataSerializer(serializers.Serializer):
    rate_date = serializers.DateField()
    rate = serializers.DecimalField(max_digits=10, decimal_places=5)


class RateChartSerializer(serializers.Serializer):
    currency_uuid = serializers.UUIDField()
    data = serializers.ListField(child=RateChartDataSerializer())
