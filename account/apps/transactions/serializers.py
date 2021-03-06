from attr import field
from rest_framework import serializers
from transactions.models import Transaction


class TransactionCategorySerializer(serializers.Serializer):
    name = serializers.CharField()
    parent = serializers.UUIDField()
    parent_name = serializers.CharField()


class TransactionAccountSerializer(serializers.Serializer):
    source = serializers.CharField()


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
    currency = serializers.UUIDField()
    amount = serializers.FloatField()
    spent_in_currencies = serializers.DictField(read_only=True)
    spent_in_base_currency = serializers.FloatField(read_only=True)
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


class ReportByMonthSerializer(serializers.Serializer):
    month = serializers.CharField()
    day = serializers.IntegerField()
    grouped_amount = serializers.IntegerField()
