from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from categories import constants
from transactions.models import LastViewed, Transaction


class TransactionCategorySerializer(serializers.Serializer):
    name = serializers.CharField()
    parent = serializers.UUIDField()
    parent_name = serializers.CharField()


class TransactionAccountSerializer(serializers.Serializer):
    title = serializers.CharField()


class TransactionBudgetSerializer(serializers.Serializer):
    title = serializers.CharField()


class TransactionCurrencySerializer(serializers.Serializer):
    sign = serializers.CharField()


class TransactionSpentInCurrencySerializer(serializers.Serializer):
    amount = serializers.FloatField()
    sign = serializers.CharField()
    currency = serializers.UUIDField()


class TransactionSerializer(serializers.Serializer):
    uuid = serializers.UUIDField(read_only=True)
    user = serializers.UUIDField()
    category = serializers.UUIDField()
    category_details = TransactionCategorySerializer(read_only=True)
    budget = serializers.UUIDField(allow_null=True)
    budget_details = TransactionBudgetSerializer(read_only=True, allow_null=True)
    currency = serializers.UUIDField()
    currency_details = TransactionCurrencySerializer(read_only=True, allow_null=True)
    amount = serializers.FloatField()
    spent_in_currencies = serializers.DictField(read_only=True)
    account = serializers.UUIDField()
    account_details = TransactionAccountSerializer(read_only=True)
    description = serializers.CharField(allow_blank=True, allow_null=True)
    transaction_date = serializers.CharField()
    created_at = serializers.DateTimeField(read_only=True)
    modified_at = serializers.DateTimeField(read_only=True)


class GroupedByCategorySerializer(serializers.Serializer):
    category_name = serializers.CharField()
    parent_name = serializers.CharField()
    spent_in_base_currency = serializers.FloatField()
    spent_in_currencies = serializers.DictField(read_only=True)
    items = serializers.ListField(child=TransactionSerializer())


class GroupedTransactionSerializer(serializers.Serializer):
    category_name = serializers.CharField()
    spent_in_base_currency = serializers.FloatField()
    spent_in_currencies = serializers.DictField(read_only=True)
    items = serializers.ListField(child=GroupedByCategorySerializer())

    def validate_spent_in_base_currency(self, value):
        return round(value, 4)


class TransactionCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transaction
        fields = (
            "user",
            "category",
            "budget",
            "currency",
            "amount",
            "account",
            "description",
            "transaction_date",
        )

    def create(self, validated_data):
        workspace = validated_data["user"].active_workspace
        if not workspace:
            raise ValidationError("User has no active workspace")
        category_type = validated_data["category"].type
        if category_type == constants.EXPENSE and validated_data["budget"] is None:
            raise ValidationError("Expsense should contain budget specified")
        data = {
            **validated_data,
            "workspace": workspace,
        }
        return super().create(data)


class TransactionDetailsSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transaction
        fields = (
            "uuid",
            "user",
            "category",
            "budget",
            "currency",
            "amount",
            "account",
            "description",
            "transaction_date",
            "created_at",
            "modified_at",
        )


class TransactionUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transaction
        fields = (
            "uuid",
            "user",
            "category",
            "budget",
            "currency",
            "amount",
            "account",
            "description",
            "transaction_date",
            "created_at",
            "modified_at",
        )


class ReportByMonthSerializer(serializers.Serializer):
    month = serializers.CharField()
    day = serializers.IntegerField()
    grouped_amount = serializers.FloatField()


class ReportCategoryDetailsSerializer(serializers.Serializer):
    name = serializers.CharField()
    value = serializers.FloatField()
    category_type = serializers.CharField(max_length=3)


class ReportChartSerializer(serializers.Serializer):
    date = serializers.DateField(format="%Y-%m")
    categories = serializers.ListField(child=ReportCategoryDetailsSerializer())


class IncomeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transaction
        fields = (
            "transaction_date",
            "amount",
            "currency",
        )


class LastViewedSerializer(serializers.ModelSerializer):
    class Meta:
        model = LastViewed
        fields = (
            "user",
            "transaction",
        )
