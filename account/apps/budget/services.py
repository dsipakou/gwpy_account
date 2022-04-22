import datetime
from typing import List

from budget.entities import (BudgetGroupedItem, BudgetItem,
                             BudgetTransactionItem, CategoryItem)
from budget.models import Budget
from categories.models import Category
from django.db.models import Count, Prefetch, Q
from transactions.models import Transaction


class BudgetService:
    @classmethod
    def load_budget(
        cls, date_from: datetime.date, date_to: datetime.date
    ) -> List[CategoryItem]:
        transactions = Transaction.objects.all().order_by("budget__title")

        budgets = (
            Budget.objects.filter(budget_date__lte=date_to, budget_date__gte=date_from)
            .prefetch_related(
                Prefetch(
                    "transaction_set",
                    queryset=transactions,
                    to_attr="budget_transactions",
                ),
            )
            .order_by("title")
        )

        categories = (
            Category.objects.filter()
            .prefetch_related(
                Prefetch("budget_set", queryset=budgets, to_attr="category_budgets")
            )
            .annotate(
                budget_count=Count(
                    "budget",
                    filter=Q(
                        budget__budget_date__lte=date_to,
                        budget__budget_date__gte=date_from,
                    ),
                ),
            )
            .filter(budget_count__gt=0)
            .order_by("name")
        )

        return cls.make_categories(categories)

    @classmethod
    def make_categories(cls, categories) -> List[CategoryItem]:
        categories_list = []
        for category in categories:
            budgets = cls.make_budgets(category.category_budgets)
            spent_in_base_currency = sum(
                item["spent_in_base_currency"] for item in budgets
            )
            spent_in_original_currency = sum(
                item["spent_in_original_currency"] for item in budgets
            )
            planned = sum(item["planned"] for item in budgets)
            categories_list.append(
                CategoryItem(
                    uuid=category.uuid,
                    category_name=category.name,
                    budgets=budgets,
                    planned=planned,
                    spent_in_base_currency=spent_in_base_currency,
                    spent_in_original_currency=spent_in_original_currency,
                )
            )
        return categories_list

    @classmethod
    def make_budgets(cls, budgets) -> List[BudgetItem]:
        budgets_list = []
        grouped_dict = {}
        for budget in budgets:
            transactions = cls.make_transactions(budget.budget_transactions)
            spent_in_base_currency = 0
            spent_in_original_currency = 0
            if len(transactions) > 0:
                spent_in_base_currency = sum(
                    item["spent_in_base_currency"] for item in transactions
                )
                spent_in_original_currency = sum(
                    item["spent_in_original_currency"] for item in transactions
                )
            budget_item = BudgetItem(
                uuid=budget.uuid,
                category=budget.category.uuid,
                title=budget.title,
                budget_date=budget.budget_date,
                transactions=transactions,
                description=budget.description,
                is_completed=budget.is_completed,
                planned=budget.amount,
                spent_in_base_currency=spent_in_base_currency,
                spent_in_original_currency=spent_in_original_currency,
                created_at=budget.created_at,
                modified_at=budget.modified_at,
            )
            if budget_item["title"] not in grouped_dict:
                grouped_dict[budget_item["title"]] = {
                    "uuid": budget_item["uuid"],
                    "title": budget_item["title"],
                    "planned": budget_item["planned"],
                    "spent_in_base_currency": budget_item["spent_in_base_currency"],
                    "spent_in_original_currency": budget_item[
                        "spent_in_original_currency"
                    ],
                    "items": [budget_item],
                }
            else:
                grouped_dict[budget_item["title"]]["planned"] += budget_item["planned"]
                grouped_dict[budget_item["title"]][
                    "spent_in_base_currency"
                ] += budget_item["spent_in_base_currency"]
                grouped_dict[budget_item["title"]][
                    "spent_in_original_currency"
                ] += budget_item["spent_in_original_currency"]
                grouped_dict[budget_item["title"]]["items"].append(budget_item)

        for value in grouped_dict.values():
            budgets_list.append(BudgetGroupedItem(**value))
        return budgets_list

    @classmethod
    def make_transactions(cls, transactions) -> List[BudgetTransactionItem]:
        transactions_list = []
        for transaction in transactions:
            transactions_list.append(
                BudgetTransactionItem(
                    uuid=transaction.uuid,
                    currency=transaction.currency.uuid,
                    currency_code=transaction.currency.code,
                    spent_in_base_currency=transaction.spent_in_base_currency,
                    spent_in_original_currency=transaction.amount,
                )
            )
        return transactions_list
