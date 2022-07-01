import datetime
from typing import List

from budget.entities import (BudgetGroupedItem, BudgetItem,
                             BudgetTransactionItem, CategoryItem,
                             MonthUsageSum)
from budget.models import Budget
from categories.models import Category
from dateutil.relativedelta import relativedelta
from django.db.models import Count, Prefetch, Q, Sum
from django.db.models.functions import TruncMonth
from transactions.models import Rate, Transaction


class BudgetService:
    @classmethod
    def get_archive(
        cls, current_date: datetime.date, category_uuid: str
    ) -> List[MonthUsageSum]:
        archive = []
        start_date = datetime.date.fromisoformat(current_date).replace(
            day=1
        ) - relativedelta(months=6)
        end_date = start_date + relativedelta(months=6)

        archive_sum = (
            Budget.objects.annotate(month=TruncMonth("budget_date"))
            .filter(
                budget_date__gte=start_date,
                budget_date__lt=end_date,
                category=category_uuid,
            )
            .values("month")
            .annotate(planned=Sum("amount"))
            .order_by("month")
        )

        for item in archive_sum:
            archive.append(MonthUsageSum(month=item["month"], planned=item["planned"]))

        return archive

    @classmethod
    def load_budget(
        cls, date_from: datetime.date, date_to: datetime.date
    ) -> List[CategoryItem]:
        cls.start = datetime.datetime.now()
        budgets = (
            Budget.objects.filter(budget_date__lte=date_to, budget_date__gte=date_from)
            .prefetch_related(
                Prefetch(
                    "transaction_set",
                    queryset=Transaction.objects.select_related("currency").all(),
                    to_attr="budget_transactions",
                ),
            )
            .order_by("title")
        )

        rates = Rate.objects.filter(
            rate_date__lte=date_to, rate_date__gte=date_from
        ).prefetch_related("currency")
        rates_dict = {(rate.currency.uuid, rate.rate_date): rate.rate for rate in rates}

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

        return cls.make_categories(categories, rates_dict)

    @classmethod
    def load_weekly_budget(cls, date_from, date_to) -> List[BudgetItem]:
        budgets = Budget.objects.filter(
            budget_date__lte=date_to, budget_date__gte=date_from
        ).prefetch_related(
            Prefetch(
                "transaction_set",
                queryset=Transaction.objects.all(),
                to_attr="budget_transactions",
            ),
        )

        rates = Rate.objects.filter(rate_date__lte=date_to, rate_date__gte=date_from)
        rates_dict = {(rate.currency.uuid, rate.rate_date): rate.rate for rate in rates}

        return cls.make_budgets(budgets, rates_dict)

    @classmethod
    def make_categories(cls, categories, rates) -> List[CategoryItem]:
        categories_list = []
        for category in categories:
            budgets = cls.make_grouped_budgets(category.category_budgets, rates)
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
    def make_grouped_budgets(cls, budgets, rates) -> List[BudgetGroupedItem]:
        budgets_list = []
        grouped_dict = {}
        for budget in cls.make_budgets(budgets, rates):
            if budget["title"] not in grouped_dict:
                grouped_dict[budget["title"]] = {
                    "uuid": budget["uuid"],
                    "title": budget["title"],
                    "planned": budget["planned"],
                    "spent_in_base_currency": budget["spent_in_base_currency"],
                    "spent_in_original_currency": budget["spent_in_original_currency"],
                    "items": [budget],
                }
            else:
                grouped_dict[budget["title"]]["planned"] += budget["planned"]
                grouped_dict[budget["title"]]["spent_in_base_currency"] += budget[
                    "spent_in_base_currency"
                ]
                grouped_dict[budget["title"]]["spent_in_original_currency"] += budget[
                    "spent_in_original_currency"
                ]
                grouped_dict[budget["title"]]["items"].append(budget)

        for value in grouped_dict.values():
            budgets_list.append(BudgetGroupedItem(**value))
        return budgets_list

    @classmethod
    def make_budgets(cls, budgets, rates) -> List[BudgetItem]:
        budgets_list = []
        for budget in budgets:
            transactions = cls.make_transactions(budget.budget_transactions, rates)
            spent_in_base_currency = 0
            spent_in_original_currency = 0
            if len(transactions) > 0:
                spent_in_base_currency = sum(
                    item["spent_in_base_currency"] for item in transactions
                )
                spent_in_original_currency = sum(
                    item["spent_in_original_currency"] for item in transactions
                )
            budgets_list.append(
                BudgetItem(
                    uuid=budget.uuid,
                    category=budget.category.uuid,
                    title=budget.title,
                    budget_date=budget.budget_date,
                    transactions=transactions,
                    description=budget.description,
                    recurrent=budget.recurrent,
                    is_completed=budget.is_completed,
                    planned=budget.amount,
                    spent_in_base_currency=spent_in_base_currency,
                    spent_in_original_currency=spent_in_original_currency,
                    created_at=budget.created_at,
                    modified_at=budget.modified_at,
                )
            )
        return budgets_list

    @classmethod
    def make_transactions(cls, transactions, rates) -> List[dict]:
        transactions_list = []
        for transaction in transactions:
            if transaction.currency.is_base:
                spent_in_base_currency = transaction.amount
            else:
                spent_in_base_currency = (
                    rates.get(
                        (transaction.currency.uuid, transaction.transaction_date), 0
                    )
                    * transaction.amount
                )
            transactions_list.append(
                BudgetTransactionItem(
                    uuid=transaction.uuid,
                    currency=transaction.currency.uuid,
                    currency_code=transaction.currency.code,
                    spent_in_base_currency=spent_in_base_currency,
                    spent_in_original_currency=transaction.amount,
                )
            )
        return transactions_list
