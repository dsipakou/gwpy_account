import datetime
from uuid import UUID

import structlog
from dateutil.relativedelta import relativedelta
from dateutil.rrule import MONTHLY, rrule
from django.db.models import Count, FloatField, Prefetch, Q, QuerySet, Sum, Value
from django.db.models.fields.json import KeyTextTransform
from django.db.models.functions import Cast, Coalesce, Round, TruncMonth

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
    MonthUsageSum,
)
from budget.exceptions import UnsupportedDuplicateTypeError
from budget.models import Budget, BudgetMulticurrency
from categories import constants
from currencies.models import Currency
from rates.models import Rate
from rates.utils import generate_amount_map
from transactions.models import Transaction
from users.models import User
from workspaces.models import Workspace

RECURRENT_TYPE_MAPPING = {
    BudgetDuplicateType.MONTHLY: {
        "start_date": utils.get_first_day_of_prev_month,
        "end_date": utils.get_last_day_of_prev_month,
        "relative_date": relativedelta(months=1),
        "relative_usage": relativedelta(months=5),
    },
    BudgetDuplicateType.WEEKLY: {
        "start_date": utils.get_first_day_of_prev_week,
        "end_date": utils.get_last_day_of_prev_week,
        "relative_date": relativedelta(weeks=1),
        "relative_usage": relativedelta(weeks=5),
    },
    BudgetDuplicateType.OCCASIONAL: {
        "start_date": utils.get_first_day_of_prev_month,
        "end_date": utils.get_last_day_of_prev_month,
        "relative_date": relativedelta(months=1),
        "relative_usage": relativedelta(months=6),
        "lookback_months": 6,
    },
}

logger = structlog.get_logger()


class BudgetService:
    @classmethod
    def create_budget_multicurrency_amount(
        cls, uuids: list[UUID], workspace: Workspace
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
        budgets_qs: QuerySet,
        categories_qs: QuerySet,
        currencies_qs: QuerySet,
        transactions_qs: QuerySet,
        date_from: str,
        date_to: str,
        user: str | None,
    ):
        budgets = (
            budgets_qs.filter(budget_date__lte=date_to, budget_date__gte=date_from)
            .select_related("currency", "category", "multicurrency", "user")
            .order_by("budget_date")
        )
        parent_categories = categories_qs.filter(
            parent__isnull=True, type=constants.EXPENSE
        ).order_by("name")

        available_currencies = list(currencies_qs.values("code", "is_base"))
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
        categories_map = {}

        date_from_parsed = datetime.datetime.strptime(date_from, "%Y-%m-%d").date()
        date_to_parsed = datetime.datetime.strptime(date_to, "%Y-%m-%d").date()

        # Create map of all categories from workspace with minimum data
        for category in parent_categories:
            categories_map[category.uuid] = CategoryModel.init(
                category, available_currencies
            )

        # Create grouped budgets with budgets inside for corresponding categories
        # Counting only planned values here
        for budget in budgets:
            category_for_budget = categories_map[budget.category.uuid]

            transaction_budget_group_key = GroupedBudgetModel.get_grouped_budget_key(
                budget
            )

            # If this budget group isn't exists yet in this category - create it
            if transaction_budget_group_key not in category_for_budget.budgets_map:
                category_for_budget.budgets_map[transaction_budget_group_key] = (
                    GroupedBudgetModel.init(
                        budget,
                        available_currencies,
                    )
                )

            budget_group_item = category_for_budget.budgets_map[
                transaction_budget_group_key
            ]

            # Add budget to budget group
            budget_group_item.items_map[budget.uuid] = BudgetModel.init(
                budget,
                available_currencies,
            )

            # Increase planned values with real budget value
            # TODO: remove this since this value are obsolete
            budget_group_item.planned += budget.amount
            category_for_budget.planned += budget.amount

            budget_group_item.update_planned_values(
                available_currencies, budget.multicurrency_map
            )
            category_for_budget.update_planned_values(
                available_currencies, budget.multicurrency_map
            )

        # Fill in budgets spendings
        for transaction in transactions:
            # Prepare transaction model
            transaction_model = BudgetTransactionModel.init(transaction)

            transaction_budget = transaction.budget
            transaction_budget_group_key = GroupedBudgetModel.get_grouped_budget_key(
                transaction_budget
            )

            # Actual transaction category might differ from budget category
            transaction_category = transaction.category.parent

            # TODO: make a migration to rid off nullable budgets
            # Legacy support when transaction can be without a budget
            if not transaction_budget:
                continue

            transaction_category_object = categories_map[transaction_category.uuid]

            # TODO: Remove this
            transaction_category_object.spent += transaction.amount
            transaction_category_object.update_spent_values(
                available_currencies, transaction.multicurrency_map
            )

            # Find or append budget group to category
            # title + uuid + year-month uniqueness
            if (
                transaction_budget_group_key
                not in transaction_category_object.budgets_map
            ):
                transaction_category_object.budgets_map[
                    transaction_budget_group_key
                ] = GroupedBudgetModel.build_for_transaction(
                    transaction_budget,
                    transaction_category_object,
                    date_from_parsed,
                    date_to_parsed,
                    available_currencies,
                )

            budget_group_item = transaction_category_object.budgets_map[
                transaction_budget_group_key
            ]

            budget_group_item.spent += transaction.amount
            budget_group_item.update_spent_values(
                available_currencies, transaction.multicurrency_map
            )
            budget_group_item.update_spent_overall_values(
                available_currencies, transaction.multicurrency_map
            )

            # Find or append budget to budget group
            if transaction_budget.uuid not in budget_group_item.items_map:
                budget_group_item.items_map[transaction_budget.uuid] = (
                    BudgetModel.init_for_transaction(
                        transaction_budget, available_currencies
                    )
                )

            simple_budget_item = budget_group_item.items_map[transaction_budget.uuid]

            simple_budget_item.spent += transaction.amount
            simple_budget_item.update_spent_values(
                available_currencies, transaction.multicurrency_map
            )
            simple_budget_item.transactions.append(transaction_model)

            # Logic when transaction and budget categories are no the same
            transaction_budget_category = transaction_budget.category
            if transaction_category != transaction_budget_category:
                transaction_budget_category_object = categories_map[
                    transaction_budget_category.uuid
                ]
                if (
                    transaction_budget_group_key
                    not in transaction_budget_category_object.budgets_map
                ):
                    transaction_budget_category_object.budgets_map[
                        transaction_budget_group_key
                    ] = GroupedBudgetModel.build_for_transaction(
                        transaction_budget,
                        transaction_category_object,
                        date_from_parsed,
                        date_to_parsed,
                        available_currencies,
                    )
                simple_budget_grouped_budget_item = (
                    transaction_budget_category_object.budgets_map[
                        transaction_budget_group_key
                    ]
                )
                simple_budget_grouped_budget_item.update_spent_overall_values(
                    available_currencies, transaction.multicurrency_map
                )
                if (
                    transaction_budget.uuid
                    not in simple_budget_grouped_budget_item.items_map
                ):
                    simple_budget_grouped_budget_item.items_map[
                        transaction_budget.uuid
                    ] = BudgetModel.init_for_transaction(
                        transaction_budget, available_currencies
                    )
                simple_budget_budget_item = simple_budget_grouped_budget_item.items_map[
                    transaction_budget.uuid
                ]
                if transaction_category != transaction_budget_category:
                    simple_budget_budget_item.transactions.append(transaction_model)

        # Prepare output list
        output = list(categories_map.values())
        for cat in output:
            cat.budgets = list(cat.budgets_map.values())
            for bud in cat.budgets:
                bud.items = list(bud.items_map.values())

        return [item.dict() for item in output]

    @classmethod
    def load_budget(
        cls,
        queryset: QuerySet,
        categories_qs: QuerySet,
        currency_qs: QuerySet,
        date_from: datetime.date,
        date_to: datetime.date,
        user: str | None,
    ) -> list[CategoryItem]:
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
            queryset=budgets.filter(workspace=user.active_workspace),
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
        user: str | None,
    ) -> list[BudgetItem]:
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
        base_currency = available_currencies.filter(is_base=True).first()
        if not base_currency:
            return []

        return cls.make_budgets(
            budgets,
            cls._get_latest_rates(),
            available_currencies,
            base_currency["code"],
        )

    # TODO: obsolete, was used in old montyly usage calculator
    # review and delete if needed
    @classmethod
    def make_categories(
        cls, currency_qs: QuerySet, categories, latest_rates
    ) -> list[CategoryItem]:
        categories_list = []
        eval_categories = list(categories)
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
    ) -> list[BudgetGroupedItem]:
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
                    ) + budget["spent_in_currencies"].get(currency["code"], 0)

                    grouped_dict[budget["title"]]["planned_in_currencies"][
                        currency["code"]
                    ] = grouped_dict[budget["title"]]["planned_in_currencies"].get(
                        currency["code"], 0
                    ) + budget["planned_in_currencies"].get(currency["code"], 0)
                grouped_dict[budget["title"]]["items"].append(budget)

        for value in grouped_dict.values():
            budgets_list.append(BudgetGroupedItem(**value))
        return budgets_list

    @classmethod
    def make_budgets(
        cls, budgets, latest_rates, available_currencies, base_currency
    ) -> list[BudgetItem]:
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
                    planned_in_currencies[currency["code"]] = (
                        budget.multicurrency.amount_map[currency["code"]]
                    )
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
    ) -> list[dict]:
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
        cls, qs, recurrent_type: BudgetDuplicateType, pivot_date: str | None = None
    ) -> list[dict[datetime.date, str]]:
        if RECURRENT_TYPE_MAPPING.get(recurrent_type) is None:
            raise UnsupportedDuplicateTypeError

        start_date = RECURRENT_TYPE_MAPPING[recurrent_type]["start_date"](pivot_date)
        end_date = RECURRENT_TYPE_MAPPING[recurrent_type]["end_date"](pivot_date)

        items = (
            qs.filter(
                Q(recurrent=BudgetDuplicateType.OCCASIONAL.value)
                | (
                    Q(recurrent=recurrent_type)
                    & Q(budget_date__range=(start_date, end_date))
                )
            )
            .prefetch_related("currency")
            .order_by("budget_date")
        )

        usage_end_date = RECURRENT_TYPE_MAPPING[recurrent_type]["end_date"]()
        usage_start_date = (
            RECURRENT_TYPE_MAPPING[recurrent_type]["start_date"]()
            - RECURRENT_TYPE_MAPPING[recurrent_type]["relative_usage"]
        )

        transactions = Transaction.objects.filter(
            budget__title__in=items.values_list("title", flat=True),
            transaction_date__gte=usage_start_date,
            transaction_date__lte=usage_end_date,
        ).select_related("multicurrency", "budget__currency")

        output = []
        for item in items:
            usage_sum = (
                transactions.filter(budget__title=item.title)
                .values("budget__uuid", "budget__title")
                .annotate(
                    total_in_currency=Round(
                        Sum(
                            Coalesce(
                                Cast(
                                    KeyTextTransform(
                                        item.currency.code, "multicurrency__amount_map"
                                    ),
                                    FloatField(),
                                ),
                                Value(0, output_field=FloatField()),
                            )
                        ),
                        2,
                    )
                )
            )
            all_sums = [value["total_in_currency"] for value in usage_sum]
            avg_sum = (
                round(sum(all_sums) / len(all_sums), 2) if all_sums else item.amount
            )
            upcoming_item_date = (
                item.budget_date
                + RECURRENT_TYPE_MAPPING[recurrent_type]["relative_date"]
            )
            existing_item = Budget.objects.filter(
                Q(
                    title=item.title,
                    budget_date=upcoming_item_date,
                )
            )
            if not existing_item.exists():
                output.append(
                    {
                        "uuid": item.uuid,
                        "date": upcoming_item_date,
                        "title": item.title,
                        "amount": avg_sum,
                        "currency": item.currency.sign,
                        "recurrent": item.recurrent,
                    }
                )

        return output

    @classmethod
    def duplicate_budget(cls, budgets: list[dict[str, int]], workspace: Workspace):
        for budget in budgets:
            budget_item = Budget.objects.get(uuid=budget["uuid"])
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
                    amount=budget["value"] or budget_item.amount,
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
        filter_by_user: str | None = None,
    ) -> list[MonthUsageSum]:
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
        all_months = rrule(
            MONTHLY,
            dtstart=six_month_earlier,
            until=selected_month_first_day - relativedelta(months=1),
        )

        # add empty months with 0 amount
        clean_transactions: list[MonthUsageSum] = []
        for current_month in all_months:
            if transaction := grouped_transactions.filter(month=current_month).first():
                amount = transaction.get("amount", 0)
            else:
                amount = 0
            clean_transactions.append(
                MonthUsageSum(
                    month=current_month.date(),
                    amount=amount,
                )
            )
        return clean_transactions
