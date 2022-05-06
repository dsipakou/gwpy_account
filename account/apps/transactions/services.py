from typing import List, Optional

from transactions.entities import (GroupedTransaction,
                                   TransactionAccountDetails,
                                   TransactionCategoryDetails, TransactionItem,
                                   TransactionSpentInCurrencyDetails)
from transactions.models import Transaction


class TransactionService:
    @classmethod
    def get_transaction(cls, transaction: Transaction) -> Optional[Transaction]:
        category_details = TransactionCategoryDetails(
            name=transaction.category.name,
            parent=transaction.category.parent.uuid,
            parent_name=transaction.category.parent.name,
        )
        account_details = TransactionAccountDetails(
            source=transaction.account.source,
        )
        spent_details = [
            TransactionSpentInCurrencyDetails(
                amount=transaction.amount * rate.rate,
                sign=rate.currency.sign,
                currency=rate.currency.uuid,
            )
            for rate in transaction.to_date_rates
        ]

        return TransactionItem(
            uuid=transaction.uuid,
            user=transaction.user.uuid,
            category=transaction.category.uuid,
            category_details=category_details,
            budget=transaction.budget,
            currency=transaction.currency.uuid,
            amount=transaction.amount,
            spent_in_base_currency=transaction.spent_in_base_currency,
            spent_in_currency_list=spent_details,
            account=transaction.account.uuid,
            account_details=account_details,
            description=transaction.description,
            transaction_date=transaction.transaction_date,
            created_at=transaction.created_at,
            modified_at=transaction.modified_at,
        )

    @classmethod
    def load_transaction(cls, transaction_uuid: str) -> TransactionItem:
        transaction = Transaction.objects.get(uuid=transaction_uuid)
        return cls.get_transaction(transaction)

    @classmethod
    def load_transactions(
        cls,
        *,
        limit: Optional[int] = 15,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        order_by: Optional[str] = "created_at",
    ) -> List[TransactionItem]:
        transactions = []
        qs = (
            Transaction.objects.all()
            .order_by(f"-{order_by}")
            .select_related("category", "account")[:limit]
        )

        for transaction in qs:
            transactions.append(cls.get_transaction(transaction))
        return transactions

    @classmethod
    def load_grouped_transactions(
        cls, *, date_from: Optional[str] = None, date_to: Optional[str] = None
    ) -> List[GroupedTransaction]:
        grouped_transactions = {}
        transactions = []
        qs = Transaction.objects.all().order_by("-created_at")
        if date_from:
            qs = qs.filter(transaction_date__gte=date_from)
        if date_to:
            qs = qs.filter(transaction_date__lte=date_to)

        for transaction in qs:
            transaction_details: TransactionItem = cls.get_transaction(transaction)
            parent_name = transaction_details["category_details"]["parent_name"]
            grouped_transactions[parent_name] = grouped_transactions.get(
                parent_name, []
            )
            grouped_transactions[parent_name].append(transaction_details)
        for key in sorted(grouped_transactions.keys()):
            transactions.append(
                GroupedTransaction(category_name=key, items=grouped_transactions[key])
            )
        return transactions
