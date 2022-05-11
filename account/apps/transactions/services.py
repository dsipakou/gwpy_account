import copy
from typing import TYPE_CHECKING, List, Optional

from django.db.models import QuerySet
from transactions.entities import (GroupedByCategory, GroupedByParent,
                                   TransactionAccountDetails,
                                   TransactionCategoryDetails, TransactionItem,
                                   TransactionSpentInCurrencyDetails)
from transactions.models import Transaction

AMOUNT_ACCURACY = 6


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
        spent_details = {
            rate.currency.code: TransactionSpentInCurrencyDetails(
                amount=round(transaction.amount / rate.rate, AMOUNT_ACCURACY),
                sign=rate.currency.sign,
                currency=rate.currency.uuid,
            )
            for rate in transaction.to_date_rates
        }

        return TransactionItem(
            uuid=transaction.uuid,
            user=transaction.user.uuid,
            category=transaction.category.uuid,
            category_details=category_details,
            budget=transaction.budget,
            currency=transaction.currency.uuid,
            amount=transaction.amount,
            spent_in_base_currency=transaction.spent_in_base_currency,
            spent_in_currencies=spent_details,
            account=transaction.account.uuid,
            account_details=account_details,
            description=transaction.description,
            transaction_date=transaction.transaction_date,
            created_at=transaction.created_at,
            modified_at=transaction.modified_at,
        )

    @classmethod
    def group_by_category(cls, transactions: QuerySet) -> GroupedByCategory:
        grouped_by_category = {}
        for transaction in transactions:
            transaction_details: TransactionItem = cls.get_transaction(transaction)
            category_name = transaction_details["category_details"]["name"]
            parent_name = transaction_details["category_details"]["parent_name"]
            if category_name not in grouped_by_category:
                grouped_by_category[category_name] = GroupedByCategory(
                    category_name=category_name,
                    parent_name=parent_name,
                    spent_in_base_currency=transaction_details[
                        "spent_in_base_currency"
                    ],
                    spent_in_currencies=copy.deepcopy(
                        transaction_details["spent_in_currencies"]
                    ),
                    items=[transaction_details],
                )
                continue

            grouped_by_category[category_name]["items"].append(transaction_details)

            grouped_by_category[category_name]["spent_in_base_currency"] = round(
                grouped_by_category[category_name]["spent_in_base_currency"]
                + transaction_details["spent_in_base_currency"],
                AMOUNT_ACCURACY,
            )

            for currency, value in grouped_by_category[category_name][
                "spent_in_currencies"
            ].items():
                grouped_by_category[category_name]["spent_in_currencies"][currency][
                    "amount"
                ] = round(
                    value["amount"]
                    + transaction_details["spent_in_currencies"][currency]["amount"],
                    AMOUNT_ACCURACY,
                )
        return grouped_by_category

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
    ) -> List[GroupedByParent]:

        grouped_by_category = {}
        transactions = []
        qs = Transaction.objects.all().order_by("-created_at")
        if date_from:
            qs = qs.filter(transaction_date__gte=date_from)
        if date_to:
            qs = qs.filter(transaction_date__lte=date_to)

        grouped_by_parent = {}
        grouped_by_category = cls.group_by_category(qs)

        for category in sorted(grouped_by_category.keys()):
            grouped_by_parent[
                grouped_by_category[category]["parent_name"]
            ] = grouped_by_parent.get(grouped_by_category[category]["parent_name"], [])
            grouped_by_parent[grouped_by_category[category]["parent_name"]].append(
                grouped_by_category[category]
            )

        for key in sorted(grouped_by_parent.keys()):
            transactions.append(
                GroupedByParent(category_name=key, items=grouped_by_parent[key])
            )
        return transactions
