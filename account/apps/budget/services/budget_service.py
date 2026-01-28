import datetime
import warnings
from uuid import UUID

import structlog
from dateutil.relativedelta import relativedelta
from dateutil.rrule import MONTHLY, rrule
from django.db.models import FloatField, Prefetch, QuerySet, Sum, Value
from django.db.models.fields.json import KeyTextTransform
from django.db.models.functions import Cast, Coalesce, TruncMonth

from budget import utils
from budget.constants import BudgetDuplicateType
from budget.entities import (
    BudgetGroupedItem,
    BudgetItem,
    BudgetModel,
    BudgetTransactionModel,
    CategoryModel,
    GroupedBudgetModel,
    MonthUsageSum,
)
from budget.models import BudgetSeries
from budget.services.duplication_service import (
    BudgetDuplicationService,
)
from budget.services.entity_transformer import BudgetEntityTransformer
from budget.services.multicurrency_service import BudgetMulticurrencyService
from budget.services.series_service import BudgetSeriesService
from categories import constants
from transactions.models import Transaction
from users.models import User
from workspaces.models import Workspace

logger = structlog.get_logger()


class BudgetService:
    @classmethod
    def create_budget_multicurrency_amount(
        cls, uuids: list[UUID], workspace: Workspace
    ):
        """Create or update multicurrency amounts for budgets.

        DEPRECATED: Use BudgetMulticurrencyService.create_budget_multicurrency_amount instead.
        This wrapper will be removed in a future release.
        """
        warnings.warn(
            "BudgetService.create_budget_multicurrency_amount is deprecated. "
            "Use BudgetMulticurrencyService.create_budget_multicurrency_amount instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return BudgetMulticurrencyService.create_budget_multicurrency_amount(
            uuids, workspace
        )

    @classmethod
    def _calculate_occurrences(
        cls, series: BudgetSeries, to_date: datetime.date | datetime.datetime
    ) -> list[datetime.date]:
        """Calculate occurrence dates for a budget series.

        DEPRECATED: Use BudgetSeriesService.calculate_occurrences instead.
        This wrapper will be removed in a future release.
        """
        warnings.warn(
            "BudgetService._calculate_occurrences is deprecated. "
            "Use BudgetSeriesService.calculate_occurrences instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return BudgetSeriesService.calculate_occurrences(series, to_date)

    @classmethod
    def _calculate_smart_amount(
        cls, series: BudgetSeries, use_smart_amount: bool = False
    ) -> float:
        """Calculate smart budget amount based on historical spending.

        DEPRECATED: Use BudgetSeriesService.calculate_smart_amount instead.
        This wrapper will be removed in a future release.
        """
        warnings.warn(
            "BudgetService._calculate_smart_amount is deprecated. "
            "Use BudgetSeriesService.calculate_smart_amount instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return BudgetSeriesService.calculate_smart_amount(series, use_smart_amount)

    @classmethod
    def materialize_budgets(
        cls,
        workspace: Workspace,
        date_to: datetime.datetime,
    ) -> None:
        """Materialize budget series into individual Budget instances.

        DEPRECATED: Use BudgetSeriesService.materialize_budgets instead.
        This wrapper will be removed in a future release.
        """
        warnings.warn(
            "BudgetService.materialize_budgets is deprecated. "
            "Use BudgetSeriesService.materialize_budgets instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return BudgetSeriesService.materialize_budgets(workspace, date_to)

    @staticmethod
    def _get_latest_rates():
        """Get the latest exchange rate for each currency.

        DEPRECATED: Use BudgetMulticurrencyService._get_latest_rates instead.
        This wrapper will be removed in a future release.
        """
        warnings.warn(
            "BudgetService._get_latest_rates is deprecated. "
            "Use BudgetMulticurrencyService._get_latest_rates instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return BudgetMulticurrencyService._get_latest_rates()

    @classmethod
    def _initialize_category_map(cls, parent_categories, available_currencies) -> dict:
        """Create map of all categories from workspace with minimum data.

        Args:
            parent_categories: QuerySet of parent Category models
            available_currencies: List of currency dicts with code and is_base

        Returns:
            Dict mapping category UUID to CategoryModel instances
        """
        categories_map = {}
        for category in parent_categories:
            categories_map[category.uuid] = CategoryModel.init(
                category, available_currencies
            )
        return categories_map

    @classmethod
    def _populate_budget_groups(cls, budgets, categories_map, available_currencies):
        """Create grouped budgets with planned values.

        Args:
            budgets: QuerySet of Budget models
            categories_map: Dict mapping category UUID to CategoryModel
            available_currencies: List of currency dicts with code and is_base

        Mutates categories_map by adding budget groups and planned values.
        """
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

    @classmethod
    def _populate_budget_spending(
        cls,
        transactions,
        categories_map,
        available_currencies,
        date_from_parsed,
        date_to_parsed,
    ):
        """Fill in budget spending from transactions.

        Args:
            transactions: QuerySet of Transaction models
            categories_map: Dict mapping category UUID to CategoryModel
            available_currencies: List of currency dicts with code and is_base
            date_from_parsed: Start date as datetime.date
            date_to_parsed: End date as datetime.date

        Mutates categories_map by adding transaction spending to budgets.
        """
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

    @classmethod
    def _finalize_output(cls, categories_map) -> list[dict]:
        """Convert category map to output list format.

        Args:
            categories_map: Dict mapping category UUID to CategoryModel

        Returns:
            List of category dicts with nested budgets and items
        """
        output = list(categories_map.values())
        for cat in output:
            cat.budgets = list(cat.budgets_map.values())
            for bud in cat.budgets:
                bud.items = list(bud.items_map.values())

        return [item.dict() for item in output]

    @classmethod
    def load_budget_v2(
        cls,
        *,
        workspace: Workspace,
        budgets_qs: QuerySet,
        categories_qs: QuerySet,
        currencies_qs: QuerySet,
        transactions_qs: QuerySet,
        date_from: str,
        date_to: str,
        user: str | None,
    ):
        """Generate monthly budget report with spending analysis.

        This method orchestrates the budget reporting workflow:
        1. Materialize budget series for the period
        2. Initialize category structure
        3. Populate planned budget values
        4. Add transaction spending data
        5. Format output for API response

        Args:
            workspace: Workspace to filter data
            budgets_qs: QuerySet of Budget models
            categories_qs: QuerySet of Category models
            currencies_qs: QuerySet of Currency models
            transactions_qs: QuerySet of Transaction models
            date_from: Start date string (YYYY-MM-DD)
            date_to: End date string (YYYY-MM-DD)
            user: Optional user UUID to filter budgets/transactions

        Returns:
            List of category dicts with nested budget groups and items
        """
        # Materialize recurring budgets for the period
        date_to_formatted = utils.get_end_of_current_week_datetime(date_to)
        cls.materialize_budgets(workspace, date_to_formatted)

        # Query budgets and categories for the period
        budgets = (
            budgets_qs.filter(budget_date__lte=date_to, budget_date__gte=date_from)
            .select_related("currency", "category", "multicurrency", "user", "series")
            .order_by("budget_date")
        )
        parent_categories = categories_qs.filter(
            parent__isnull=True, type=constants.EXPENSE
        ).order_by("name")

        # Query transactions with related data
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

        # Parse date strings once
        date_from_parsed = datetime.datetime.strptime(date_from, "%Y-%m-%d").date()
        date_to_parsed = datetime.datetime.strptime(date_to, "%Y-%m-%d").date()

        # Build category map with budget groups and spending
        categories_map = cls._initialize_category_map(
            parent_categories, available_currencies
        )
        cls._populate_budget_groups(budgets, categories_map, available_currencies)
        cls._populate_budget_spending(
            transactions,
            categories_map,
            available_currencies,
            date_from_parsed,
            date_to_parsed,
        )

        # Format output for API
        return cls._finalize_output(categories_map)

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
        date_to_formatted = utils.get_end_of_current_week_datetime(date_to)
        cls.materialize_budgets(workspace, date_to_formatted)
        budgets = (
            qs.filter(budget_date__lte=date_to, budget_date__gte=date_from)
            .select_related("series")
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

    @classmethod
    def make_grouped_budgets(
        cls, budgets, latest_rates, available_currencies, base_currency
    ) -> list[BudgetGroupedItem]:
        """Group budgets by title and aggregate spending/planning.

        DEPRECATED: Use BudgetEntityTransformer.group_budgets instead.
        This wrapper will be removed in a future release.
        """
        warnings.warn(
            "BudgetService.make_grouped_budgets is deprecated. "
            "Use BudgetEntityTransformer.group_budgets instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return BudgetEntityTransformer.group_budgets(
            budgets, latest_rates, available_currencies, base_currency
        )

    @classmethod
    def make_budgets(
        cls, budgets, latest_rates, available_currencies, base_currency
    ) -> list[BudgetItem]:
        """Transform budget QuerySet into BudgetItem TypedDicts.

        DEPRECATED: Use BudgetEntityTransformer.transform_to_budget_items instead.
        This wrapper will be removed in a future release.
        """
        warnings.warn(
            "BudgetService.make_budgets is deprecated. "
            "Use BudgetEntityTransformer.transform_to_budget_items instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return BudgetEntityTransformer.transform_to_budget_items(
            budgets, latest_rates, available_currencies, base_currency
        )

    @classmethod
    def make_transactions(
        cls, transactions, latest_rates, base_currency_code: str
    ) -> list[dict]:
        """Transform transaction QuerySet into TypedDict list.

        DEPRECATED: Use BudgetEntityTransformer.transform_transactions instead.
        This wrapper will be removed in a future release.
        """
        warnings.warn(
            "BudgetService.make_transactions is deprecated. "
            "Use BudgetEntityTransformer.transform_transactions instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return BudgetEntityTransformer.transform_transactions(
            transactions, latest_rates, base_currency_code
        )

    @classmethod
    def get_duplicate_budget_candidates(
        cls, qs, recurrent_type: BudgetDuplicateType, pivot_date: str | None = None
    ) -> list[dict[datetime.date, str]]:
        """Find budgets that can be duplicated for the next period.

        DEPRECATED: Use BudgetDuplicationService.get_duplicate_candidates instead.
        This wrapper will be removed in a future release.

        LEGACY: This is part of the old manual duplication system.
        For new recurring budgets, use BudgetSeries instead.
        """
        warnings.warn(
            "BudgetService.get_duplicate_budget_candidates is deprecated. "
            "Use BudgetDuplicationService.get_duplicate_candidates instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return BudgetDuplicationService.get_duplicate_candidates(
            qs, recurrent_type, pivot_date
        )

    @classmethod
    def duplicate_budget(cls, budgets: list[dict[str, int]], workspace: Workspace):
        """Duplicate budgets for the next period.

        DEPRECATED: Use BudgetDuplicationService.duplicate_budgets instead.
        This wrapper will be removed in a future release.

        LEGACY: This is part of the old manual duplication system.
        For new recurring budgets, use BudgetSeries instead.
        """
        warnings.warn(
            "BudgetService.duplicate_budget is deprecated. "
            "Use BudgetDuplicationService.duplicate_budgets instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return BudgetDuplicationService.duplicate_budgets(budgets, workspace)

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
