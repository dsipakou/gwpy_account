from rest_framework import serializers
from transactions.models import Transaction


class TransactionSerializer(serializers.ModelSerializer):
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
