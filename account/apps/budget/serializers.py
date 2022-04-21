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


class ActualUsageBudgetSerializer(serializers.Serializer):
    uuid = serializers.UUIDField(source="budget.uuid")
    title = serializers.CharField(source="budget.title")
    planned = serializers.IntegerField(source="budget.amount")
    budget_date = serializers.DateField(source="budget.budget_date")
    category = serializers.UUIDField(source="budget.category.uuid")
    category_name = serializers.CharField(source="budget.category.name")
    description = serializers.CharField(source="budget.description")
    is_completed = serializers.BooleanField(source="budget.is_completed")
    spent_in_original_currency = serializers.FloatField(source="amount")
    currency_code = serializers.CharField(source="currency.code")
    created_at = serializers.DateTimeField(source="budget.created_at")
    spent_in_base_currency = serializers.FloatField()
    modified_at = serializers.DateTimeField(source="budget.modified_at")


class TransactionSerializer(serializers.Serializer):
    currency = serializers.UUIDField(source="currency.uuid")
    currency_code = serializers.CharField(source="currency.code")
    spent_in_original_currency = serializers.FloatField(source="amount")
    spent_in_base_currency = serializers.FloatField()


class BudgetUsageSerializer(serializers.Serializer):
    uuid = serializers.UUIDField()
    title = serializers.CharField()
    planned = serializers.IntegerField(source="amount")
    budget_date = serializers.DateField()
    category = serializers.UUIDField(source="category.uuid")
    category_name = serializers.CharField(source="category.name")
    description = serializers.CharField()
    is_completed = serializers.BooleanField()
    description = serializers.CharField(allow_blank=True, allow_null=True)
    budget_transactions = serializers.ListField(child=TransactionSerializer())
    created_at = serializers.DateTimeField()
    modified_at = serializers.DateTimeField()


class CategoryBudgetSerializer(serializers.Serializer):
    category = serializers.UUIDField(source="uuid")
    category_name = serializers.CharField(source="name")
    category_budgets = serializers.ListField(child=BudgetUsageSerializer())
    budget_count = serializers.IntegerField()
