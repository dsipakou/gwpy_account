import uuid
from locale import currency
from unicodedata import category

from categories.models import Category
from rest_framework import serializers
from transactions.models import Transaction


class TransactionCategorySerializer(serializers.Serializer):
    uuid = serializers.UUIDField()
    name = serializers.CharField()
    parent = serializers.UUIDField(source="parent.uuid")
    parent_name = serializers.CharField(source="parent.name")


class TransactionAccountSerializer(serializers.Serializer):
    uuid = serializers.UUIDField()
    source = serializers.CharField()


class TransactionSerializer(serializers.Serializer):
    uuid = serializers.UUIDField()
    user = serializers.UUIDField(source="user.uuid")
    category = serializers.UUIDField(source="category.uuid")
    category_details = TransactionCategorySerializer(source="category", read_only=True)
    budget = serializers.UUIDField(source="budget.uuid", allow_null=True)
    currency = serializers.UUIDField(source="currency.uuid")
    amount = serializers.FloatField()
    spent_in_base_currency = serializers.FloatField()
    account = serializers.UUIDField(source="account.uuid")
    account_details = TransactionAccountSerializer(source="account", read_only=True)
    description = serializers.CharField(allow_blank=True, allow_null=True)
    transaction_date = serializers.CharField()
    created_at = serializers.DateTimeField()
    modified_at = serializers.DateTimeField()
