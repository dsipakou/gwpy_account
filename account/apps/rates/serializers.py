from rest_framework import serializers

from rates.models import Rate


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

    def create(self, validated_data):
        user = self.context["request"].user
        Rate.objects.create(
            workspace=user.active_workspace,
            **validated_data,
        )


class BatchedRateItemSerializer(serializers.Serializer):
    currency = serializers.CharField()
    rate = serializers.CharField()


class CreateBatchedRateSerializer(serializers.Serializer):
    rate_date = serializers.DateField()
    base_currency = serializers.CharField()
    user = serializers.SerializerMethodField()
    items = BatchedRateItemSerializer(many=True)

    def get_user(self, obj):
        user = self.context["request"].user
        return user.uuid


class RateChartDataSerializer(serializers.Serializer):
    rate_date = serializers.DateField()
    rate = serializers.DecimalField(max_digits=10, decimal_places=5)


class RateChartSerializer(serializers.Serializer):
    currency_uuid = serializers.UUIDField()
    data = serializers.ListField(child=RateChartDataSerializer())


class AvailableRates(serializers.Serializer):
    currency_code = serializers.CharField()
    rate = serializers.FloatField()
    rate_date = serializers.DateField()
