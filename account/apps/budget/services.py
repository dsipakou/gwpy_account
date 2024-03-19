import datetime
import logging
from typing import Dict, List, Optional
from uuid import UUID

from budget import utils
from budget.constants import BudgetDuplicateType
from budget.entities import (
    BudgetGroupedItem,
    BudgetItem,
    BudgetModel,
    BudgetTransactionItem,
    BudgetTransactionModel,
    CategoryItem,
    CategoryModel,
    GroupedBudgetModel,
)
from budget.exceptions import UnsupportedDuplicateTypeError
from budget.models import Budget, BudgetMulticurrency
from categories import constants
from currencies.models import Currency
from dateutil.relativedelta import relativedelta
from django.db.models import Count, FloatField, Prefetch, Q, QuerySet, Sum, Value
from django.db.models.fields.json import KeyTextTransform
from django.db.models.functions import Cast, Coalesce, TruncMonth
from rates.models import Rate
from rates.utils import generate_amount_map
from transactions.models import Rate, Transaction
from users.models import User
from workspaces.models import Workspace

from account.apps.categories.constants import INCOME

RECURRENT_TYPE_MAPPING = {
    BudgetDuplicateType.MONTHLY: {
        "start_date": utils.get_first_day_of_prev_month,
        "end_date": utils.get_last_day_of_prev_month,
        "relative_date": relativedelta(months=1),
    },
    BudgetDuplicateType.WEEKLY: {
        "start_date": utils.get_first_day_of_prev_week,
        "end_date": utils.get_last_day_of_prev_week,
        "relative_date": relativedelta(weeks=1),
    },
}

logger = logging.getLogger(__name__)


class BudgetService:
    @classmethod
    def create_budget_multicurrency_amount(
        cls, uuids: List[UUID], workspace: Workspace
    ):
        budgets = Budget.objects.select_related("currency").filter(uuid__in=uuids)
        dates = budgets.values_list("budget_date", flat=True).distinct()
        rates_on_date = Rate.objects.filter(rate_date__in=dates)
        for budget in budgets:
            amount_map = generate_amount_map(budget, rates_on_date, workspace=workspace)

            BudgetMulticurrency.objects.update_or_create(
                budget=budget, defaults={"amount_map": amount_map}
            )

    @staticmethod
    def _get_latest_rates():
        latest_rates = {}
        for currency in Currency.objects.all():
            rate = Rate.objects.filter(currency=currency).order_by("-rate_date").first()
            if rate:
                latest_rates[currency.code] = rate.rate
        return latest_rates

    @classmethod
    def load_budget_v2(
        cls,
        *,
        queryset: QuerySet,
        categories_qs: QuerySet,
        currencies_qs: QuerySet,
        transactions_qs: QuerySet,
        date_from: str,
        date_to: str,
        user: Optional[str],
    ):
        budgets = (
            queryset.filter(budget_date__lte=date_to, budget_date__gte=date_from)
            .select_related("currency", "category", "multicurrency", "user")
            .order_by("budget_date")
        )
        categories = categories_qs.filter(
            parent__isnull=True, type=constants.EXPENSE
        ).order_by("name")

        category_list = list(categories)
        available_currencies = currencies_qs.values("code", "is_base")
        transactions = transactions_qs.filter(
            transaction_date__lte=date_to,
            transaction_date__gte=date_from,
            category__type=constants.EXPENSE,
        )
        if user:
            transactions = transactions.filter(budget__user__uuid=user)
            budgets = budgets.filter(user__uuid=user)

        transactions = transactions.select_related(
            "multicurrency",
            "budget",
            "budget__category",
            "currency",
            "category",
            "category__parent",
            "user",
        )
        transactions_eval = [transaction for transaction in transactions]

        """
        Helper for keeping uuid -> index map

        Example

        {
            UUID('7b73d927-5f23-4d0f-a4d5-593727e24fb3'): {
              'index': 0,
              'items': {}
            },
            UUID('b1771ca2-0a8a-4f0a-bdec-d0af56cc022e'): {
              'index': 1,
              'items': {}
            },
            UUID('3a1c8476-126b-4820-a760-e20a0721edd7'): {
                'index': 2,
                'items': {
                    'category 1 3a1c8476-126b-4820-a760-e20a0721edd7': {
                        'index': 0,
                        'items': {
                            UUID('4c0d91fe-77c1-4e2f-a4d5-00fe3f99a77c'): {'index': 0, 'items': {}}
                        }
                    },
                    'category 2 3a1c8476-126b-4820-a760-e20a0721edd7': {
                        'index': 1,
                        'items': {UUID('8fe09547-1df4-429e-8b31-9ec4b7a5c54f'): {'index': 0, 'items': {}}}
                    }
                }
            },
        }
        """

        index_helper = {}

        grouped_categories = []
        date_from_parsed = datetime.datetime.strptime(date_from, "%Y-%m-%d").date()
        date_to_parsed = datetime.datetime.strptime(date_to, "%Y-%m-%d").date()

        # Add empty categories
        for category in category_list:
            if category.uuid not in index_helper:
                grouped_categories.append(
                    CategoryModel(
                        uuid=category.uuid,
                        category_name=category.name,
                        spent_in_currencies={
                            currency["code"]: 0 for currency in available_currencies
                        },
                        planned_in_currencies={
                            currency["code"]: 0 for currency in available_currencies
                        },
                    )
                )
                index_helper[category.uuid] = {
                    "index": len(grouped_categories) - 1,
                    "items": {},
                }

        # Add empty budgets
        for budget in budgets:
            category_helper = index_helper[budget.category.uuid]
            category_item = grouped_categories[category_helper["index"]]

            # title + uuid + year-month uniqueness
            grouped_budget_key = (
                budget.title
                + str(budget.category.uuid)
                + date_from_parsed.strftime("%Y-%m")
            )
            if grouped_budget_key not in category_helper["items"]:
                category_item.budgets.append(
                    GroupedBudgetModel(
                        user=budget.user.uuid,
                        title=budget.title,
                        spent_in_currencies={
                            currency["code"]: 0 for currency in available_currencies
                        },
                        planned_in_currencies={
                            currency["code"]: 0 for currency in available_currencies
                        },
                    )
                )
                category_helper["items"][grouped_budget_key] = {
                    "index": len(category_item.budgets) - 1,
                    "items": {},
                }
            grouped_budget_helper = category_helper["items"][grouped_budget_key]
            grouped_budget_item = category_item.budgets[grouped_budget_helper["index"]]

            if budget.uuid not in grouped_budget_helper["items"]:
                grouped_budget_item.items.append(
                    BudgetModel(
                        uuid=budget.uuid,
                        user=budget.user.uuid,
                        category=budget.category.uuid,
                        currency=budget.currency.uuid,
                        title=budget.title,
                        budget_date=budget.budget_date,
                        category_name=budget.category.name,
                        description=budget.description,
                        is_completed=budget.is_completed,
                        recurrent=budget.recurrent,
                        planned=budget.amount,
                        planned_in_currencies={
                            currency["code"]: budget.multicurrency_map.get(
                                currency["code"], 0
                            )
                            for currency in available_currencies
                        },
                        spent_in_currencies={
                            currency["code"]: 0 for currency in available_currencies
                        },
                        created_at=budget.created_at,
                        modified_at=budget.modified_at,
                    )
                )

                grouped_budget_helper["items"][budget.uuid] = {
                    "index": len(grouped_budget_item.items) - 1,
                    "items": {},
                }

                category_helper = index_helper[budget.category.uuid]
                category_item = grouped_categories[category_helper["index"]]

                grouped_budget_item.spent = 0
                category_item.spent = 0
                grouped_budget_item.planned += budget.amount
                category_item.planned += budget.amount

                for currency in available_currencies:
                    grouped_budget_item.spent_in_currencies[currency["code"]] = 0
                    category_item.spent_in_currencies[currency["code"]] = 0
                    grouped_budget_item.planned_in_currencies[
                        currency["code"]
                    ] = grouped_budget_item.planned_in_currencies.get(
                        currency["code"], 0
                    ) + budget.multicurrency_map.get(
                        currency["code"], 0
                    )
                    category_item.planned_in_currencies[
                        currency["code"]
                    ] = category_item.planned_in_currencies.get(
                        currency["code"], 0
                    ) + budget.multicurrency_map.get(
                        currency["code"], 0
                    )

        # Fill in budgets
        for transaction in transactions_eval:
            # Prepare transaction model
            transaction_model = BudgetTransactionModel(
                uuid=transaction.uuid,
                user=transaction.user.uuid,
                currency=transaction.currency.uuid,
                currency_code=transaction.currency.code,
                spent=transaction.amount,
                transaction_date=transaction.transaction_date,
                spent_in_currencies=transaction.multicurrency_map.copy(),
            )

            # Find or append category to response
            parent_category = transaction.category.parent
            if parent_category.uuid not in index_helper:
                grouped_categories.append(
                    CategoryModel(
                        uuid=parent_category.uuid,
                        category_name=parent_category.name,
                    )
                )
                index_helper[parent_category.uuid] = {
                    "index": len(grouped_categories) - 1,
                    "items": {},
                }

            budget = transaction.budget

            # TODO: make a migration to rid off nullable budgets
            # Legacy support when transaction can be without a budget
            if not budget:
                continue

            category_helper = index_helper[parent_category.uuid]
            category_item = grouped_categories[category_helper["index"]]

            category_item.spent += transaction.amount

            for currency in available_currencies:
                category_item.spent_in_currencies[
                    currency["code"]
                ] = category_item.spent_in_currencies.get(
                    currency["code"], 0
                ) + transaction.multicurrency_map.get(
                    currency["code"], 0
                )

            # Find or append budget group to category
            # title + uuid + year-month uniqueness
            grouped_budget_key = (
                budget.title
                + str(budget.category.uuid)
                + budget.budget_date.strftime("%Y-%m")
            )
            if grouped_budget_key not in category_helper["items"]:
                category_item.budgets.append(
                    GroupedBudgetModel(
                        user=budget.user.uuid,
                        title=budget.title,
                        is_another_category=category_item.uuid != budget.category.uuid,
                        is_another_month=budget.budget_date < date_from_parsed
                        or budget.budget_date > date_to_parsed,
                        planned=0,
                        planned_in_currencies={
                            currency["code"]: 0 for currency in available_currencies
                        },
                    )
                )
                category_helper["items"][grouped_budget_key] = {
                    "index": len(category_item.budgets) - 1,
                    "items": {},
                }
            grouped_budget_helper = category_helper["items"][grouped_budget_key]
            grouped_budget_item = category_item.budgets[grouped_budget_helper["index"]]

            grouped_budget_item.spent += transaction.amount

            for currency in available_currencies:
                grouped_budget_item.spent_in_currencies[
                    currency["code"]
                ] = grouped_budget_item.spent_in_currencies.get(
                    currency["code"], 0
                ) + transaction.multicurrency_map.get(
                    currency["code"], 0
                )

            # Find or append budget to budget group
            if budget.uuid not in grouped_budget_helper["items"]:
                grouped_budget_item.items.append(
                    BudgetModel(
                        uuid=budget.uuid,
                        user=budget.user.uuid,
                        category=budget.category.uuid,
                        currency=budget.currency.uuid,
                        title=budget.title,
                        budget_date=budget.budget_date,
                        category_name=budget.category.name,
                        description=budget.description,
                        is_completed=budget.is_completed,
                        recurrent=budget.recurrent,
                        created_at=budget.created_at,
                        modified_at=budget.modified_at,
                        planned=0,
                        planned_in_currencies={
                            currency["code"]: 0 for currency in available_currencies
                        },
                    )
                )

                grouped_budget_helper["items"][budget.uuid] = {
                    "index": len(grouped_budget_item.items) - 1,
                    "items": {},
                }
            budget_helper = grouped_budget_helper["items"][budget.uuid]
            budget_item = grouped_budget_item.items[budget_helper["index"]]

            budget_item.spent += transaction.amount
            budget_item.transactions.append(transaction_model)

            for currency in available_currencies:
                budget_item.spent_in_currencies[
                    currency["code"]
                ] = budget_item.spent_in_currencies.get(
                    currency["code"], 0
                ) + transaction.multicurrency_map.get(
                    currency["code"], 0
                )

        return [item.dict() for item in grouped_categories]

    @classmethod
    def load_budget(
        cls,
        queryset: QuerySet,
        categories_qs: QuerySet,
        currency_qs: QuerySet,
        date_from: datetime.date,
        date_to: datetime.date,
        user: Optional[str],
    ) -> List[CategoryItem]:
        cls.start = datetime.datetime.now()
        logger.debug("budget.service.transaction_prefetch.start")
        budget_transactions_prefetch = Prefetch(
            "transaction_set",
            queryset=Transaction.objects.select_related(
                "currency", "multicurrency"
            ).filter(budget__in=queryset),
            to_attr="transactions",
        )
        budgets = (
            queryset.filter(budget_date__lte=date_to, budget_date__gte=date_from)
            .prefetch_related(budget_transactions_prefetch)
            .select_related("currency", "category", "multicurrency", "user")
            .order_by("budget_date")
        )

        if user:
            budgets = budgets.filter(user__uuid=user)

        category_budgets_prefetch = Prefetch(
            "budget_set",
            queryset=budgets.all(),
            to_attr="budgets",
        )
        categories = (
            categories_qs.filter(parent__isnull=True, type=constants.EXPENSE)
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
            .order_by("name")
        )

        category_list = list(categories)
        return cls.make_categories(currency_qs, category_list, cls._get_latest_rates())

    @classmethod
    def load_weekly_budget(
        cls,
        qs: QuerySet,
        currency_qs: QuerySet,
        date_from,
        date_to,
        workspace: Workspace,
        user: Optional[str],
    ) -> List[BudgetItem]:
        budgets = (
            qs.filter(budget_date__lte=date_to, budget_date__gte=date_from)
            .prefetch_related(
                Prefetch(
                    "transaction_set",
                    queryset=Transaction.objects.select_related("multicurrency").filter(
                        budget__in=qs
                    ),
                    to_attr="transactions",
                ),
            )
            .all()
            .order_by("created_at")
        )
        if user:
            budgets = budgets.filter(user__uuid=user)

        available_currencies = currency_qs.values("code", "is_base")
        base_currency = available_currencies.get(is_base=True)["code"]

        return cls.make_budgets(
            budgets,
            cls._get_latest_rates(),
            available_currencies,
            base_currency,
        )

    # TODO: obsolete, was used in old montyly usage calculator
    # review and delete if needed
    @classmethod
    def make_categories(
        cls, currency_qs: QuerySet, categories, latest_rates
    ) -> List[CategoryItem]:
        categories_list = []
        eval_categories = [category for category in categories]
        available_currencies = currency_qs.values("code", "is_base")
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
                    "planned_in_currencies": budget["planned_in_currencies"].copy(),
                    "spent_in_base_currency": budget["spent_in_base_currency"],
                    "spent_in_original_currency": budget["spent_in_original_currency"],
                    "spent_in_currencies": budget["spent_in_currencies"].copy(),
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
            multicurrency_map = (
                budget.multicurrency.amount_map
                if hasattr(budget, "multicurrency")
                else {}
            )
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
                    hasattr(budget, "multicurrency")
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
                logger.debug(
                    "budget.services.make_budgets.transactions.currencies.start"
                )
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
            multicurrency_map = (
                transaction.multicurrency.amount_map
                if hasattr(transaction, "multicurrency")
                else {}
            )
            spent_in_base_currency = transaction.amount
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
        cls, qs, recurrent_type: BudgetDuplicateType, pivot_date: Optional[str] = None
    ) -> List[Dict[datetime.date, str]]:
        if RECURRENT_TYPE_MAPPING.get(recurrent_type) is None:
            raise UnsupportedDuplicateTypeError

        items = qs.filter(
            recurrent=recurrent_type,
            budget_date__gte=RECURRENT_TYPE_MAPPING[recurrent_type]["start_date"](
                pivot_date
            ),
            budget_date__lte=RECURRENT_TYPE_MAPPING[recurrent_type]["end_date"](
                pivot_date
            ),
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
    def duplicate_budget(cls, uuids: List[str], workspace: Workspace):
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
                    workspace=budget_item.workspace,
                )

                cls.create_budget_multicurrency_amount(
                    [budget.uuid], workspace=workspace
                )

    @classmethod
    def get_last_months_usage(
        cls,
        *,
        transactions: QuerySet,
        month: datetime.date,
        category_uuid: str,
        user: User,
        filter_by_user: Optional[str] = None,
    ):
        currency_code = user.currency_code()
        if not currency_code:
            return

        selected_month_first_day = month.replace(day=1)
        six_month_earlier = month - relativedelta(months=6)

        transactions = transactions.filter(
            category__parent=category_uuid,
            transaction_date__lt=selected_month_first_day,
            transaction_date__gte=six_month_earlier,
        ).prefetch_related("multicurrency")

        if filter_by_user:
            transactions = transactions.filter(user=filter_by_user)

        # get values for current default currency only
        grouped_transactions = transactions.annotate(
            current_currency_amount=Coalesce(
                Cast(
                    KeyTextTransform(currency_code, "multicurrency__amount_map"),
                    FloatField(),
                ),
                Value(0, output_field=FloatField()),
            )
        )
        # trunc dates to months
        grouped_transactions = grouped_transactions.annotate(
            month=TruncMonth("transaction_date")
        ).values("month")
        # group spent amount by months
        grouped_transactions = grouped_transactions.annotate(
            amount=Sum("current_currency_amount")
        ).order_by("month")
        return grouped_transactions
