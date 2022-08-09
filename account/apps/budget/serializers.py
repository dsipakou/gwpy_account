from budget import constants
from budget.models import Budget
from rest_framework import serializers
from rest_framework.exceptions import ValidationError


class BudgetSerializer(serializers.ModelSerializer):
    class Meta:
        model = Budget
        fields = (
            "uuid",
            "user",
            "category",
            "currency",
            "title",
            "amount",
            "recurrent",
            "budget_date",
            "description",
            "is_completed",
            "created_at",
            "modified_at",
        )


class PlannedBudgetSerializer(serializers.Serializer):
    uuid = serializers.UUIDField()
    user = serializers.UUIDField(source="user.uuid")
    category = serializers.UUIDField(source="category.uuid")
    currency = serializers.UUIDField(source="currency.uuid")
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
    uuid = serializers.UUIDField()
    currency = serializers.UUIDField()
    currency_code = serializers.CharField()
    spent_in_original_currency = serializers.FloatField()
    spent_in_base_currency = serializers.FloatField()


class BudgetUsageSerializer(serializers.Serializer):
    uuid = serializers.UUIDField()
    title = serializers.CharField()
    planned = serializers.IntegerField()
    budget_date = serializers.DateField()
    category = serializers.UUIDField()
    is_completed = serializers.BooleanField()
    recurrent = serializers.CharField()
    description = serializers.CharField(allow_blank=True, allow_null=True)
    transactions = serializers.ListField(child=TransactionSerializer())
    spent_in_original_currency = serializers.FloatField()
    spent_in_base_currency = serializers.FloatField()
    created_at = serializers.DateTimeField()
    modified_at = serializers.DateTimeField()


class ArchiveSerializer(serializers.Serializer):
    month = serializers.DateField()
    planned = serializers.IntegerField()


class WeeklyBudgetUsageSerializer(serializers.Serializer):
    uuid = serializers.UUIDField()
    title = serializers.CharField()
    budget_date = serializers.DateField()
    planned = serializers.IntegerField(source="amount")
    spent_in_original_currency = serializers.FloatField()
    spent_in_base_currency = serializers.FloatField()
    description = serializers.CharField(allow_blank=True, allow_null=True)
    is_completed = serializers.BooleanField()
    budget_transactions = serializers.ListField(child=TransactionSerializer())
    created_at = serializers.DateTimeField()
    modified_at = serializers.DateTimeField()


class BudgetGroupedUsageSerializer(serializers.Serializer):
    uuid = serializers.UUIDField()
    title = serializers.CharField()
    planned = serializers.IntegerField()
    spent_in_original_currency = serializers.FloatField()
    spent_in_base_currency = serializers.FloatField()
    items = serializers.ListField(child=BudgetUsageSerializer())


class CategoryBudgetSerializer(serializers.Serializer):
    uuid = serializers.UUIDField()
    category_name = serializers.CharField()
    budgets = serializers.ListField(child=BudgetGroupedUsageSerializer())
    planned = serializers.FloatField()
    spent_in_original_currency = serializers.FloatField()
    spent_in_base_currency = serializers.FloatField()


class DuplicateRequestSerializer(serializers.Serializer):
    uuids = serializers.ListField()

    def validate_type(self, value):
        if value not in constants.ALLOWED_BUDGET_RECURRENT_TYPE:
            return ValidationError("Unsupported budget reccurent type")
        return value


class DuplicateResponseSerializer(serializers.Serializer):
    uuid = serializers.UUIDField()
    date = serializers.DateField()
    title = serializers.CharField()
