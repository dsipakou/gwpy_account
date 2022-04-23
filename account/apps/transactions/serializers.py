import uuid
from locale import currency
from unicodedata import category

from rest_framework import serializers


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
    uuid = serializers.UUIDField()
    user = serializers.UUIDField()
    category = serializers.UUIDField()
    category_details = TransactionCategorySerializer(read_only=True)
    budget = serializers.UUIDField(allow_null=True)
    currency = serializers.UUIDField()
    amount = serializers.FloatField()
    spent_in_currency_list = serializers.ListField(
        child=TransactionSpentInCurrencySerializer()
    )
    spent_in_base_currency = serializers.FloatField()
    account = serializers.UUIDField()
    account_details = TransactionAccountSerializer(read_only=True)
    description = serializers.CharField(allow_blank=True, allow_null=True)
    transaction_date = serializers.CharField()
    created_at = serializers.DateTimeField()
    modified_at = serializers.DateTimeField()
