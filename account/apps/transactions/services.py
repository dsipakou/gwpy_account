import copy
import datetime
from typing import Dict, List, Optional
from uuid import UUID

from categories import constants as category_constants
from categories.models import Category
from django.db.models import QuerySet
from rates.models import Rate
from rates.utils import generate_amount_map
from transactions.entities import (GroupedByCategory, GroupedByMonth,
                                   GroupedByParent, TransactionAccountDetails,
                                   TransactionBudgetDetails,
                                   TransactionCategoryDetails, TransactionItem,
                                   TransactionSpentInCurrencyDetails)
from transactions.models import Transaction, TransactionMulticurrency


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
            amount_mapping = generate_amount_map(transaction, rates_on_date)

            TransactionMulticurrency.objects.update_or_create(
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
        spent_details = TransactionSpentInCurrencyDetails(
            transaction.multicurrency.amount_map
        )

        budget_details = None
        if transaction.budget:
            budget_details = TransactionBudgetDetails(
                title=transaction.budget.title,
            )

        return TransactionItem(
            uuid=transaction.uuid,
            user=transaction.user.uuid,
            category=transaction.category.uuid,
            category_details=category_details,
            budget=transaction.budget.uuid if transaction.budget else None,
            budget_details=budget_details,
            currency=transaction.currency.uuid,
            amount=transaction.amount,
            spent_in_currencies=spent_details,
            account=transaction.account.uuid,
            account_details=account_details,
            description=transaction.description,
            transaction_date=transaction.transaction_date,
            created_at=transaction.created_at,
            modified_at=transaction.modified_at,
        )

    @classmethod
    def group_by_month(cls, transactions: List[Transaction]) -> List[GroupedByMonth]:
        grouped_by_month = {}
        for transaction in transactions:
            transaction_details: TransactionItem = cls.get_transaction(transaction)
            date = transaction_details["transaction_date"]
            formatted_date = f"{date.year}-{date.month}"
            grouped_by_month[formatted_date] = grouped_by_month.get(formatted_date)
            if not grouped_by_month[formatted_date]:
                grouped_by_month[formatted_date] = {
                    "month": date.month,
                    "year": date.year,
                    "spent_in_base_currency": transaction_details[
                        "spent_in_base_currency"
                    ],
                    "spent_in_currencies": transaction_details["spent_in_currencies"],
                }
            else:
                grouped_by_month[formatted_date][
                    "spent_in_base_currency"
                ] += transaction_details["spent_in_base_currency"]
                for currency in grouped_by_month[formatted_date]["spent_in_currencies"]:
                    grouped_by_month[formatted_date]["spent_in_currencies"][
                        currency
                    ] += transaction_details["spent_in_currencies"][currency]

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
                grouped_by_category[category_name]["spent_in_currencies"][
                    currency
                ] += value
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
                grouped_by_parent[parent_name]["spent_in_currencies"][currency] += value
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
        qs = Transaction.objects.all()

        if date_from and date_to:
            qs = qs.filter(
                transaction_date__lte=date_to, transaction_date__gte=date_from
            )

        qs = qs.order_by(f"-{order_by}").select_related(
            "multicurrency", "category", "account", "budget"
        )[:limit]

        return cls.proceed_transactions(qs)

    @classmethod
    def proceed_transactions(
        cls,
        queryset: QuerySet,
    ) -> List[TransactionItem]:
        transactions = []
        for transaction in queryset:
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

    @classmethod
    def get_chart_report(cls, date_from: str, date_to: str, currency_code: str):
        grouped_transactions = Transaction.grouped_by_month_and_category(
            date_from, date_to, currency_code
        )

        grouped_map = cls._get_grouped_map(grouped_transactions)

        start_date = date_from
        end_date = date_to

        month_year_list = []
        while start_date < end_date:
            month_year_list.append(start_date.strftime("%Y-%m"))
            start_date = start_date.replace(day=1) + datetime.timedelta(days=32)
            start_date = start_date.replace(day=1)

        categories_list = (
            Category.objects.values_list("name", flat=True)
            .filter(parent__isnull=True, type=category_constants.EXPENSE)
            .order_by("name")
        )

        output = []
        for date_item in month_year_list:
            current_item = {}
            current_item["date"] = date_item
            grouped_item = grouped_map.get(date_item, {})
            current_date_category_list = []
            for category in categories_list:
                categories_map = {}
                categories_map["name"] = category
                categories_map["value"] = grouped_item.get(category, 0)
                current_date_category_list.append(categories_map)
            current_item["categories"] = current_date_category_list
            output.append(current_item)

        return output

    @classmethod
    def _get_grouped_map(cls, qs):
        output = {}
        for item in qs:
            key = item["year_month"].strftime("%Y-%m")
            output[key] = output.get(key, {})
            output[key][item["category__parent__name"]] = item["parent_sum"]

        return output
