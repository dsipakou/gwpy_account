from rest_framework import serializers
from budget.models import Budget


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
