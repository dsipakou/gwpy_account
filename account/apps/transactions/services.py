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
    def create_transaction_multicurrency_amount(cls, uuids: List[UUID]):
        amount_mapping = dict()
        transactions = Transaction.objects.select_related("currency").filter(
            uuid__in=uuids
        )
        dates = transactions.values_list("transaction_date", flat=True).distinct()
        rates_on_date = Rate.objects.filter(rate_date__in=dates)
        for transaction in transactions:
            for rate in rates_on_date:
                if transaction.currency == rate.currency:
                    # current rate currency and transaction currency are the same no need to modify amount
                    amount = transaction.amount
                elif transaction.currency.is_base:
                    # transaction currency is base currency so just divide - no need to convert to base currency beforehand
                    amount = round(transaction.amount / rate.rate, 5)
                else:
                    # need to convert amount to base currency first than to current rate currency
                    current_rate = rates_on_date.get(currency=transaction.currency)
                    amount = round(
                        transaction.amount * current_rate.rate / rate.rate, 5
                    )
                amount_mapping[rate.currency.code]: amount
            # Create a record for base currency as well
            if transaction.currency.is_base:
                amount_mapping[transaction.currency.code]: transaction.amount
            elif rates_on_date:
                amount = (
                    transaction.amount
                    * rates_on_date.get(currency=transaction.currency).rate
                )
                amount_mapping[rates_on_date[0].base_currency.code]: round(amount, 5)
            TransactionAmount.objects.update_or_create(
                transaction=transaction, defaults={"amount_map": amount_mapping}
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
