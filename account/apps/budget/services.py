import datetime
from typing import Dict, List, Optional
from uuid import UUID

from budget import utils
from budget.constants import BudgetDuplicateType
from budget.entities import (BudgetGroupedItem, BudgetItem,
                             BudgetTransactionItem, CategoryItem,
                             MonthUsageSum)
from budget.exceptions import UnsupportedDuplicateTypeError
from budget.models import Budget, BudgetAmount
from categories import constants
from categories.models import Category
from dateutil.relativedelta import relativedelta
from django.db.models import Count, Prefetch, Q, Sum
from django.db.models.functions import TruncMonth
from transactions.models import Rate, Transaction

RECURRENT_TYPE_MAPPING = {
    BudgetDuplicateType.MONTHLY: {
        "start_date": utils.get_first_day_of_prev_month(),
        "end_date": utils.get_last_day_of_prev_month(),
        "relative_date": relativedelta(months=1),
    },
    BudgetDuplicateType.WEEKLY: {
        "start_date": utils.get_first_day_of_prev_week(),
        "end_date": utils.get_last_day_of_prev_week(),
        "relative_date": relativedelta(weeks=1),
    },
}


class BudgetService:
    @classmethod
    def create_budget_multicurrency_amount(cls, uuids: List[UUID]):
        budget_amounts_map = dict()
        budgets = Budget.objects.select_related("currency").filter(uuid__in=uuids)
        dates = budgets.values_list("budget_date", flat=True).distinct()
        rates_on_date = Rate.objects.filter(rate_date__in=dates)
        for budget in budgets:
            for rate in rates_on_date:
                if budget.currency == rate.currency:
                    # current rate currency and budget currency are the same no need to modify amount
                    amount = budget.amount
                elif budget.currency.is_base:
                    # budget currency is base currency so just divide - no need to convert to base currency beforehand
                    amount = round(budget.amount / rate.rate, 5)
                else:
                    # need to convert amount to base currency first than to current rate currency
                    current_rate = rates_on_date.get(currency=budget.currency)
                    amount = round(budget.amount * current_rate.rate / rate.rate, 5)
                budget_amounts_map[rate.currency.code] = amount

            # Create a record for base currency as well
            if budget.currency.is_base:
                budget_amounts_map[budget.currency.code] = budget.amount
            elif rates_on_date:
                amount = (
                    budget.amount * rates_on_date.get(currency=budget.currency).rate
                )
                budget_amounts_map[rates_on_date[0].base_currency.code] = round(
                    amount, 5
                )

            BudgetAmount.objects.update_or_create(
                budget=budget, defaults={"amount_map": budget_amounts_map}
            )

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
        cls, date_from: datetime.date, date_to: datetime.date, user: Optional[str]
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

        if user:
            budgets = budgets.filter(user__uuid=user)

        rates = Rate.objects.filter(
            rate_date__lte=date_to, rate_date__gte=date_from
        ).prefetch_related("currency")
        rates_dict = {(rate.currency.uuid, rate.rate_date): rate.rate for rate in rates}

        categories = (
            Category.objects.filter(parent__isnull=True, type=constants.EXPENSE)
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
    def load_weekly_budget(
        cls, date_from, date_to, user: Optional[str]
    ) -> List[BudgetItem]:
        budgets = Budget.objects.filter(
            budget_date__lte=date_to, budget_date__gte=date_from
        ).prefetch_related(
            Prefetch(
                "transaction_set",
                queryset=Transaction.objects.all(),
                to_attr="budget_transactions",
            ),
        )
        if user:
            budgets = budgets.filter(user__uuid=user)

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
                    "user": budget["user"],
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
                    currency=budget.currency.uuid,
                    user=budget.user.uuid,
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

    @classmethod
    def get_duplicate_budget_candidates(
        cls, recurrent_type: BudgetDuplicateType
    ) -> List[Dict[datetime.date, str]]:
        if RECURRENT_TYPE_MAPPING.get(recurrent_type) is None:
            raise UnsupportedDuplicateTypeError

        items = Budget.objects.filter(
            recurrent=recurrent_type,
            budget_date__gte=RECURRENT_TYPE_MAPPING[recurrent_type]["start_date"],
            budget_date__lte=RECURRENT_TYPE_MAPPING[recurrent_type]["end_date"],
        ).order_by("budget_date")

        output = []
        for item in items:
            upcoming_item_date = (
                item.budget_date
                + RECURRENT_TYPE_MAPPING[recurrent_type]["relative_date"]
            )
            existing_item = Budget.objects.filter(
                title=item.title,
                budget_date=upcoming_item_date,
            )
            if not existing_item.exists():
                output.append(
                    {"uuid": item.uuid, "date": upcoming_item_date, "title": item.title}
                )
        return output

    @classmethod
    def duplicate_budget(cls, uuids: List[str]):
        for uuid in uuids:
            budget_item = Budget.objects.get(uuid=uuid)
            upcoming_item_date = (budget_item.budget_date) + RECURRENT_TYPE_MAPPING[
                budget_item.recurrent
            ]["relative_date"]
            existing_item = Budget.objects.filter(
                title=budget_item.title,
                budget_date=upcoming_item_date,
            )
            if not existing_item.exists():
                budget = Budget.objects.create(
                    category=budget_item.category,
                    currency=budget_item.currency,
                    user=budget_item.user,
                    title=budget_item.title,
                    amount=budget_item.amount,
                    budget_date=upcoming_item_date,
                    description=budget_item.description,
                    recurrent=budget_item.recurrent,
                )

                cls.create_budget_multicurrency_amount([budget.uuid])
