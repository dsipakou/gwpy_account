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
from currencies.models import Currency
from dateutil.relativedelta import relativedelta
from django.db.models import Count, Max, Min, Prefetch, Q, Sum
from django.db.models.functions import TruncMonth
from rates.models import Rate
from rates.utils import generate_amount_map
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
        budgets = Budget.objects.select_related("currency").filter(uuid__in=uuids)
        dates = budgets.values_list("budget_date", flat=True).distinct()
        rates_on_date = Rate.objects.filter(rate_date__in=dates)
        for budget in budgets:
            amount_map = generate_amount_map(budget, rates_on_date)

            BudgetAmount.objects.update_or_create(
                budget=budget, defaults={"amount_map": amount_map}
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

    @staticmethod
    def _get_latest_rates():
        latest_rates = {}
        for currency in Currency.objects.all():
            rate = Rate.objects.filter(currency=currency).order_by("-rate_date").first()
            if rate:
                latest_rates[currency.code] = rate.rate
        return latest_rates

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

        min_transaction = budgets.aggregate(date=Min("transaction__transaction_date"))
        max_transaction = budgets.aggregate(date=Max("transaction__transaction_date"))

        if user:
            budgets = budgets.filter(user__uuid=user)

        rates = Rate.objects.filter(
            rate_date__lte=max_transaction["date"],
            rate_date__gte=min_transaction["date"],
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

        return cls.make_categories(categories, rates_dict, cls._get_latest_rates())

    @classmethod
    def load_weekly_budget(
        cls, date_from, date_to, user: Optional[str]
    ) -> List[BudgetItem]:
        budgets = Budget.objects.filter(
            budget_date__lte=date_to, budget_date__gte=date_from
        ).prefetch_related(
            Prefetch(
                "transaction_set",
                queryset=Transaction.objects.all().prefetch_related(
                    "calculated_amount"
                ),
                to_attr="budget_transactions",
            ),
        )
        if user:
            budgets = budgets.filter(user__uuid=user)

        min_transaction = budgets.aggregate(date=Min("transaction__transaction_date"))
        max_transaction = budgets.aggregate(date=Max("transaction__transaction_date"))

        rates = Rate.objects.filter(
            rate_date__lte=max_transaction["date"],
            rate_date__gte=min_transaction["date"],
        )
        rates_dict = {(rate.currency.uuid, rate.rate_date): rate.rate for rate in rates}

        return cls.make_budgets(budgets, rates_dict, cls._get_latest_rates())

    @classmethod
    def make_categories(cls, categories, rates, latest_rates) -> List[CategoryItem]:
        categories_list = []
        for category in categories:
            budgets = cls.make_grouped_budgets(
                category.category_budgets, rates, latest_rates
            )
            spent_in_base_currency = sum(
                item["spent_in_base_currency"] for item in budgets
            )
            spent_in_original_currency = sum(
                item["spent_in_original_currency"] for item in budgets
            )
            spent_in_currencies = {}

            for currency in Currency.objects.all():
                spent_in_currencies[currency.code] = sum(
                    budget["spent_in_currencies"].get(currency.code, 0)
                    for budget in budgets
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
                    spent_in_currencies=spent_in_currencies,
                )
            )
        return categories_list

    @classmethod
    def make_grouped_budgets(
        cls, budgets, rates, latest_rates
    ) -> List[BudgetGroupedItem]:
        budgets_list = []
        grouped_dict = {}
        for budget in cls.make_budgets(budgets, rates, latest_rates):
            if budget["title"] not in grouped_dict:
                grouped_dict[budget["title"]] = {
                    "uuid": budget["uuid"],
                    "user": budget["user"],
                    "title": budget["title"],
                    "planned": budget["planned"],
                    "spent_in_base_currency": budget["spent_in_base_currency"],
                    "spent_in_original_currency": budget["spent_in_original_currency"],
                    "spent_in_currencies": budget["spent_in_currencies"],
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
                for currency in Currency.objects.values_list("code", flat=True):
                    grouped_dict[budget["title"]]["spent_in_currencies"][
                        currency
                    ] = grouped_dict[budget["title"]]["spent_in_currencies"].get(
                        currency, 0
                    ) + budget[
                        "spent_in_currencies"
                    ].get(
                        currency, 0
                    )
                grouped_dict[budget["title"]]["items"].append(budget)

        for value in grouped_dict.values():
            budgets_list.append(BudgetGroupedItem(**value))
        return budgets_list

    @classmethod
    def make_budgets(cls, budgets, rates, latest_rates) -> List[BudgetItem]:
        budgets_list = []
        for budget in budgets:
            transactions = cls.make_transactions(
                budget.budget_transactions, rates, latest_rates
            )
            spent_in_base_currency = 0
            spent_in_original_currency = 0
            spent_in_currencies = {}
            if len(transactions) > 0:
                spent_in_base_currency = sum(
                    item["spent_in_base_currency"] for item in transactions
                )
                spent_in_original_currency = sum(
                    item["spent_in_original_currency"] for item in transactions
                )
                for currency in Currency.objects.all():
                    spent_in_currencies[currency.code] = sum(
                        transaction["spent_in_currencies"].get(currency.code, 0)
                        for transaction in transactions
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
                    spent_in_currencies=spent_in_currencies,
                    created_at=budget.created_at,
                    modified_at=budget.modified_at,
                )
            )
        return budgets_list

    @classmethod
    def make_transactions(cls, transactions, rates, latest_rates) -> List[dict]:
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
            calculated_amount = transaction.calculated_amount.amount_map
            for latest_rate in latest_rates:
                if latest_rate not in calculated_amount:
                    calculated_amount[latest_rate] = round(
                        spent_in_base_currency / latest_rates[latest_rate], 5
                    )
            transactions_list.append(
                BudgetTransactionItem(
                    uuid=transaction.uuid,
                    currency=transaction.currency.uuid,
                    currency_code=transaction.currency.code,
                    spent_in_base_currency=spent_in_base_currency,
                    spent_in_original_currency=transaction.amount,
                    spent_in_currencies=calculated_amount,
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
        print(RECURRENT_TYPE_MAPPING[recurrent_type]["start_date"])
        print(RECURRENT_TYPE_MAPPING[recurrent_type]["end_date"])
        print(items.count())

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
