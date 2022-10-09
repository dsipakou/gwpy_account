import datetime
from typing import Dict, List, Optional
from uuid import UUID
import logging

from budget import utils
from budget.constants import BudgetDuplicateType
from budget.entities import (BudgetGroupedItem, BudgetItem,
                             BudgetTransactionItem, CategoryItem,
                             MonthUsageSum)
from budget.exceptions import UnsupportedDuplicateTypeError
from budget.models import Budget, BudgetMulticurrency
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

logger = logging.getLogger(__name__)


class BudgetService:
    @classmethod
    def create_budget_multicurrency_amount(cls, uuids: List[UUID]):
        budgets = Budget.objects.select_related("currency").filter(uuid__in=uuids)
        dates = budgets.values_list("budget_date", flat=True).distinct()
        rates_on_date = Rate.objects.filter(rate_date__in=dates)
        for budget in budgets:
            amount_map = generate_amount_map(budget, rates_on_date)

            BudgetMulticurrency.objects.update_or_create(
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
        logger.info("budget.service.transaction_prefetch.start")
        budget_transactions_prefetch = Prefetch(
            "transaction_set",
            queryset=Transaction.objects.select_related(
                "currency", "multicurrency"
            ).all(),
            to_attr="transactions",
        )
        budgets = (
            Budget.objects.filter(budget_date__lte=date_to, budget_date__gte=date_from)
            .prefetch_related(budget_transactions_prefetch)
            .select_related("currency", "category", "multicurrency", "user")
            .order_by("title")
        )

        if user:
            budgets = budgets.filter(user__uuid=user)

        category_budgets_prefetch = Prefetch(
            "budget_set",
            queryset=budgets.all(),
            to_attr="budgets",
        )
        categories = (
            Category.objects.filter(parent__isnull=True, type=constants.EXPENSE)
            .prefetch_related(category_budgets_prefetch)
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

        category_list = list(categories)

        return cls.make_categories(category_list, cls._get_latest_rates())

    @classmethod
    def load_weekly_budget(
        cls, date_from, date_to, user: Optional[str]
    ) -> List[BudgetItem]:
        budgets = Budget.objects.filter(
            budget_date__lte=date_to, budget_date__gte=date_from
        ).prefetch_related(
            Prefetch(
                "transaction_set",
                queryset=Transaction.objects.select_related("multicurrency").all(),
                to_attr="transactions",
            ),
        ).all()
        if user:
            budgets = budgets.filter(user__uuid=user)

        available_currencies = Currency.objects.values("code", "is_base")
        base_currency = available_currencies.get(is_base=True)["code"]

        return cls.make_budgets(
            budgets,
            cls._get_latest_rates(),
            available_currencies,
            base_currency,
        )

    @classmethod
    def make_categories(cls, categories, latest_rates) -> List[CategoryItem]:
        categories_list = []
        eval_categories = [category for category in categories]
        available_currencies = Currency.objects.values("code", "is_base")
        base_currency = available_currencies.get(is_base=True)["code"]
        for category in eval_categories:
            budgets = cls.make_grouped_budgets(
                category.budgets,
                latest_rates,
                available_currencies,
                base_currency,
            )
            spent_in_base_currency = sum(
                item["spent_in_base_currency"] for item in budgets
            )
            spent_in_original_currency = sum(
                item["spent_in_original_currency"] for item in budgets
            )
            planned = sum(item["planned"] for item in budgets)
            planned_in_currencies = {}
            spent_in_currencies = {}
            for currency in available_currencies:
                spent_in_currencies[currency["code"]] = sum(
                    budget["spent_in_currencies"].get(currency["code"], 0)
                    for budget in budgets
                )

                planned_in_currencies[currency["code"]] = sum(
                    budget["planned_in_currencies"].get(currency["code"], 0)
                    for budget in budgets
                )

            categories_list.append(
                CategoryItem(
                    uuid=category.uuid,
                    category_name=category.name,
                    budgets=budgets,
                    planned=planned,
                    planned_in_currencies=planned_in_currencies,
                    spent_in_base_currency=spent_in_base_currency,
                    spent_in_original_currency=spent_in_original_currency,
                    spent_in_currencies=spent_in_currencies,
                )
            )
        return categories_list

    @classmethod
    def make_grouped_budgets(
        cls, budgets, latest_rates, available_currencies, base_currency
    ) -> List[BudgetGroupedItem]:
        budgets_list = []
        grouped_dict = {}
        for budget in cls.make_budgets(
            budgets, latest_rates, available_currencies, base_currency
        ):
            if budget["title"] not in grouped_dict:
                grouped_dict[budget["title"]] = {
                    "uuid": budget["uuid"],
                    "user": budget["user"],
                    "title": budget["title"],
                    "planned": budget["planned"],
                    "planned_in_currencies": budget["planned_in_currencies"],
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
                for currency in available_currencies:
                    grouped_dict[budget["title"]]["spent_in_currencies"][
                        currency["code"]
                    ] = grouped_dict[budget["title"]]["spent_in_currencies"].get(
                        currency["code"], 0
                    ) + budget[
                        "spent_in_currencies"
                    ].get(
                        currency["code"], 0
                    )

                    grouped_dict[budget["title"]]["planned_in_currencies"][
                        currency["code"]
                    ] = grouped_dict[budget["title"]]["planned_in_currencies"].get(
                        currency["code"], 0
                    ) + budget[
                        "planned_in_currencies"
                    ].get(
                        currency["code"], 0
                    )
                grouped_dict[budget["title"]]["items"].append(budget)

        for value in grouped_dict.values():
            budgets_list.append(BudgetGroupedItem(**value))
        return budgets_list

    @classmethod
    def make_budgets(
        cls, budgets, latest_rates, available_currencies, base_currency
    ) -> List[BudgetItem]:
        budgets_list = []
        for budget in budgets:
            multicurrency_map = budget.multicurrency.amount_map
            planned_in_base_currency = multicurrency_map.get(
                base_currency, budget.amount
            )
            transactions = cls.make_transactions(
                budget.transactions, latest_rates, base_currency
            )
            spent_in_original_currency = 0
            spent_in_base_currency = 0
            spent_in_currencies = {}
            planned_in_currencies = {}
            logger.debug("budget.services.make_budgets.currencies.start")
            for currency in available_currencies:
                if (
                    budget.multicurrency
                    and currency["code"] in budget.multicurrency.amount_map
                ):
                    planned_in_currencies[
                        currency["code"]
                    ] = budget.multicurrency.amount_map[currency["code"]]
                elif currency["is_base"]:
                    planned_in_currencies[currency["code"]] = planned_in_base_currency
                else:
                    try:
                        planned_in_currencies[currency["code"]] = round(
                            planned_in_base_currency
                            / latest_rates.get(currency["code"], 0),
                            5,
                        )
                    except ZeroDivisionError:
                        planned_in_currencies[currency["code"]] = 0
            logger.debug("budget.services.make_budgets.currencies.end")
            if len(transactions) > 0:
                spent_in_base_currency = sum(
                    item["spent_in_base_currency"] for item in transactions
                )
                spent_in_original_currency = sum(
                    item["spent_in_original_currency"] for item in transactions
                )
                logger.debug("budget.services.make_budgets.transactions.currencies.start")
                for currency in available_currencies:
                    spent_in_currencies[currency["code"]] = sum(
                        transaction["spent_in_currencies"].get(currency["code"], 0)
                        for transaction in transactions
                    )
                logger.debug("budget.services.make_budgets.transactions.currencies.end")
            logger.debug("budget.services.make_budgets.budget_item.start")
            budget_item = BudgetItem(
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
                planned_in_currencies=planned_in_currencies,
                spent_in_base_currency=spent_in_base_currency,
                spent_in_original_currency=spent_in_original_currency,
                spent_in_currencies=spent_in_currencies,
                created_at=budget.created_at,
                modified_at=budget.modified_at,
            )
            budgets_list.append(budget_item)
            logger.debug("budget.services.make_budgets.budget_item.end")
        return budgets_list

    @classmethod
    def make_transactions(
        cls, transactions, latest_rates, base_currency_code: str
    ) -> List[dict]:
        transactions_list = []
        for transaction in transactions:
            multicurrency_map = transaction.multicurrency.amount_map
            spent_in_base_currency = multicurrency_map[base_currency_code]
            for currency_code in latest_rates:
                if currency_code not in multicurrency_map:
                    try:
                        multicurrency_map[currency_code] = round(
                            spent_in_base_currency / latest_rates.get(currency_code, 0),
                            5,
                        )
                    except ZeroDivisionError:
                        multicurrency_map[currency_code] = 0
            logger.debug("budget.services.make_transactions.append_item.start")
            transactions_list.append(
                BudgetTransactionItem(
                    uuid=transaction.uuid,
                    currency=transaction.currency.uuid,
                    currency_code=transaction.currency.code,
                    spent_in_base_currency=spent_in_base_currency,
                    spent_in_original_currency=transaction.amount,
                    spent_in_currencies=multicurrency_map,
                    transaction_date=transaction.transaction_date,
                )
            )
            logger.debug("budget.services.make_transactions.append_item.end")
        transactions_list.sort(key=lambda x: x["transaction_date"])
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
