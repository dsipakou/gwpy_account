import copy
from typing import Dict, List, Optional
from uuid import UUID

from categories import constants as category_constants
from django.db.models import QuerySet, Sum
from rates.models import Rate
from transactions.entities import (GroupedByCategory, GroupedByParent,
                                   TransactionAccountDetails,
                                   TransactionCategoryDetails, TransactionItem,
                                   TransactionSpentInCurrencyDetails)
from transactions.models import Transaction, TransactionAmount


class TransactionService:
    @classmethod
    def create_transaction_multicurrency_amount(cls, uuid: UUID):
        transaction = Transaction.objects.get(uuid=uuid)
        rates_on_date = Rate.objects.filter(rate_date=transaction.transaction_date)
        for rate in rates_on_date:
            object, created = TransactionAmount.objects.update_or_create(
                currency=rate.currency,
                transaction=transaction,
                amount=transaction.amount * rate.rate,
            )

    @classmethod
    def get_transaction(cls, transaction: Transaction) -> Optional[Transaction]:
        category_details = TransactionCategoryDetails(
            name=transaction.category.name,
            parent=transaction.category.parent.uuid
            if transaction.category.type == category_constants.EXPENSE
            else "",
            parent_name=transaction.category.parent.name
            if transaction.category.type == category_constants.EXPENSE
            else "",
        )
        account_details = TransactionAccountDetails(
            title=transaction.account.title,
        )
        spent_details = {
            rate.currency.code: TransactionSpentInCurrencyDetails(
                amount=transaction.spent_in_base_currency / rate.rate,
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
            budget=transaction.budget.uuid if transaction.budget else None,
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

            grouped_by_category[category_name][
                "spent_in_base_currency"
            ] += transaction_details["spent_in_base_currency"]

            for currency, value in grouped_by_category[category_name][
                "spent_in_currencies"
            ].items():
                grouped_by_category[category_name]["spent_in_currencies"][currency][
                    "amount"
                ] += value["amount"]
        return grouped_by_category

    @classmethod
    def group_by_parent(
        cls, grouped_by_category: Dict[str, GroupedByCategory]
    ) -> GroupedByParent:
        grouped_by_parent = {}
        for _, category in sorted(grouped_by_category.items()):
            parent_name = category["parent_name"]
            if parent_name not in grouped_by_parent:
                grouped_by_parent[parent_name] = GroupedByParent(
                    category_name=parent_name,
                    spent_in_base_currency=category["spent_in_base_currency"],
                    spent_in_currencies=copy.deepcopy(category["spent_in_currencies"]),
                    items=[category],
                )
                continue

            grouped_by_parent[parent_name]["items"].append(category)

            grouped_by_parent[parent_name]["spent_in_base_currency"] += category[
                "spent_in_base_currency"
            ]

            for currency, value in grouped_by_parent[parent_name][
                "spent_in_currencies"
            ].items():
                grouped_by_parent[parent_name]["spent_in_currencies"][currency][
                    "amount"
                ] += value["amount"]
        return grouped_by_parent

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
        qs = Transaction.objects.all().order_by("-created_at")
        if date_from:
            qs = qs.filter(transaction_date__gte=date_from)
        if date_to:
            qs = qs.filter(transaction_date__lte=date_to)

        grouped_by_category = cls.group_by_category(qs)
        grouped_by_parent = cls.group_by_parent(grouped_by_category)

        transactions = []
        for _, value in sorted(grouped_by_parent.items()):
            transactions.append(value)
        return transactions


class ReportService:
    @classmethod
    def get_year_report(cls, date_from: str, date_to: str, currency_code: str):
        return Transaction.grouped_by_month(date_from, date_to, currency_code)
