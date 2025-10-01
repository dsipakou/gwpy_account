from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from budget import constants
from budget.models import Budget


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

    def create(self, validated_data):
        workspace = validated_data["user"].active_workspace
        if not workspace:
            raise ValidationError("User has no active workspace")
        data = {
            **validated_data,
            "workspace": workspace,
        }
        return super().create(data)


class TransactionSerializer(serializers.Serializer):
    uuid = serializers.UUIDField()
    currency = serializers.UUIDField()
    currency_code = serializers.CharField()
    spent_in_original_currency = serializers.FloatField()
    spent_in_base_currency = serializers.FloatField()
    spent_in_currencies = serializers.DictField()
    transaction_date = serializers.CharField()


class TransactionV2Serializer(serializers.Serializer):
    uuid = serializers.UUIDField()
    currency = serializers.UUIDField()
    currency_code = serializers.CharField()
    spent = serializers.FloatField()
    spent_in_currencies = serializers.DictField()
    transaction_date = serializers.CharField()


class BudgetUsageSerializer(serializers.Serializer):
    uuid = serializers.UUIDField()
    title = serializers.CharField()
    planned = serializers.FloatField()
    planned_in_currencies = serializers.DictField()
    budget_date = serializers.DateField()
    category = serializers.UUIDField()
    currency = serializers.UUIDField()
    user = serializers.UUIDField()
    is_completed = serializers.BooleanField()
    recurrent = serializers.CharField()
    description = serializers.CharField(allow_blank=True, allow_null=True)
    transactions = serializers.ListField(child=TransactionSerializer())
    spent_in_original_currency = serializers.FloatField()
    spent_in_base_currency = serializers.FloatField()
    spent_in_currencies = serializers.DictField()
    created_at = serializers.DateTimeField()
    modified_at = serializers.DateTimeField()


class BudgetUsageV2Serializer(serializers.Serializer):
    uuid = serializers.UUIDField()
    title = serializers.CharField()
    budget_date = serializers.DateField()
    category = serializers.UUIDField()
    currency = serializers.UUIDField()
    user = serializers.UUIDField()
    is_completed = serializers.BooleanField()
    recurrent = serializers.CharField()
    description = serializers.CharField(allow_blank=True, allow_null=True)
    transactions = serializers.ListField(child=TransactionV2Serializer())
    planned = serializers.FloatField()
    spent = serializers.FloatField()
    planned_in_currencies = serializers.DictField()
    spent_in_currencies = serializers.DictField()
    created_at = serializers.DateTimeField()
    modified_at = serializers.DateTimeField()


class WeeklyBudgetUsageSerializer(serializers.Serializer):
    uuid = serializers.UUIDField()
    title = serializers.CharField()
    budget_date = serializers.DateField()
    planned = serializers.FloatField(source="amount")
    spent_in_original_currency = serializers.FloatField()
    spent_in_base_currency = serializers.FloatField()
    description = serializers.CharField(allow_blank=True, allow_null=True)
    is_completed = serializers.BooleanField()
    budget_transactions = serializers.ListField(child=TransactionSerializer())
    created_at = serializers.DateTimeField()
    modified_at = serializers.DateTimeField()


class BudgetGroupedUsageSerializer(serializers.Serializer):
    uuid = serializers.UUIDField()
    user = serializers.UUIDField()
    title = serializers.CharField()
    planned = serializers.IntegerField()
    planned_in_currencies = serializers.DictField()
    spent_in_original_currency = serializers.FloatField()
    spent_in_base_currency = serializers.FloatField()
    spent_in_currencies = serializers.DictField()
    items = serializers.ListField(child=BudgetUsageSerializer())


class BudgetGroupedUsageV2Serializer(serializers.Serializer):
    uuid = serializers.UUIDField()
    user = serializers.UUIDField()
    title = serializers.CharField()
    planned = serializers.IntegerField()
    spent = serializers.FloatField()
    is_another_category = serializers.BooleanField()
    is_another_month = serializers.BooleanField()
    planned_in_currencies = serializers.DictField()
    spent_in_currencies = serializers.DictField()
    spent_in_currencies_overall = serializers.DictField()
    items = serializers.ListField(child=BudgetUsageV2Serializer())


class CategoryBudgetSerializer(serializers.Serializer):
    uuid = serializers.UUIDField()
    category_name = serializers.CharField()
    budgets = serializers.ListField(child=BudgetGroupedUsageSerializer())
    planned = serializers.FloatField()
    planned_in_currencies = serializers.DictField()
    spent_in_original_currency = serializers.FloatField()
    spent_in_base_currency = serializers.FloatField()
    spent_in_currencies = serializers.DictField()


class CategoryBudgetV2Serializer(serializers.Serializer):
    uuid = serializers.UUIDField()
    category_name = serializers.CharField()
    budgets = serializers.ListField(child=BudgetGroupedUsageV2Serializer())
    planned = serializers.FloatField()
    spent = serializers.FloatField()
    planned_in_currencies = serializers.DictField()
    spent_in_currencies = serializers.DictField()


class LastMonthsUsageSerializer(serializers.Serializer):
    month = serializers.DateField()
    amount = serializers.FloatField()

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["amount"] = round(data["amount"], 0)
        return data


class DuplicateRequestSerializer(serializers.Serializer):
    budgets = serializers.ListField()

    def validate_type(self, value):
        if value not in constants.ALLOWED_BUDGET_RECURRENT_TYPE:
            return ValidationError("Unsupported budget reccurent type")
        return value


class DuplicateResponseSerializer(serializers.Serializer):
    uuid = serializers.UUIDField()
    date = serializers.DateField()
    title = serializers.CharField()
    amount = serializers.FloatField()
    currency = serializers.CharField()
    recurrent = serializers.CharField()
