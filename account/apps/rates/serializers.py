from rates.models import Rate
from rest_framework import serializers


class RateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Rate
        fields = (
            "uuid",
            "currency",
            "rate_date",
            "rate",
            "description",
            "created_at",
            "modified_at",
        )
