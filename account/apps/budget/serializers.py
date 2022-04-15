from budget.models import Budget
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
