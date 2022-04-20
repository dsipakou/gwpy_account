from budget.models import Budget
from categories.serializers import CategorySerializer
from rest_framework import serializers


class BudgetSerializer(serializers.ModelSerializer):
    class Meta:
        model = Budget
        fields = (
            "uuid",
            "category",
            "title",
            "amount",
            "budget_date",
            "description",
            "is_completed",
            "created_at",
            "modified_at",
        )


class PlannedBudgetSerializer(serializers.Serializer):
    uuid = serializers.UUIDField()
    category = serializers.UUIDField(source="category.uuid")
    title = serializers.CharField()
    amount = serializers.IntegerField()
    budget_date = serializers.DateField()
    description = serializers.CharField(allow_blank=True, allow_null=True)
    is_completed = serializers.BooleanField()
    created_at = serializers.DateTimeField()
    modified_at = serializers.DateTimeField()
    category_name = serializers.CharField(source="category.name")
