import datetime
import warnings
from uuid import UUID

import structlog
from dateutil.relativedelta import relativedelta
from dateutil.rrule import MONTHLY, WEEKLY, rrule
from django.db.models import FloatField, Prefetch, Q, QuerySet, Sum, Value
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
    CategoryModel,
    GroupedBudgetModel,
    MonthUsageSum,
)
from budget.exceptions import UnsupportedDuplicateTypeError
from budget.models import Budget, BudgetSeries
from budget.services.multicurrency_service import BudgetMulticurrencyService
from categories import constants
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
        # Convert to_date to date if it's a datetime
        if isinstance(to_date, datetime.datetime):
            to_date = to_date.date()

        # For monthly series, use relativedelta to handle month-end edge cases
        # (e.g., Jan 31 -> Feb 28 -> Mar 31, keeping the original day when possible)
        if str(series.frequency) == "MONTHLY":
            occurrences = []
            start_date = series.start_date
            end_date = series.until or to_date
            count = series.count

            if count:
                skipped_count = series.exceptions.filter(is_skipped=True).count()
                count = count + skipped_count

            occurrence_num = 0
            while True:
                if count and occurrence_num >= count:
                    break

                # Calculate date by adding months to the start date
                # This preserves the original day when possible
                current_date = start_date + relativedelta(
                    months=series.interval * occurrence_num  # type: ignore[arg-type]
                )

                if current_date > end_date:
                    break

                occurrences.append(current_date)
                occurrence_num += 1

            return occurrences
        else:
            # For weekly and other frequencies, use rrule
            freq_map = {
                "WEEKLY": WEEKLY,
                "MONTHLY": MONTHLY,
            }

            count = series.count
            if count:
                skipped_count = series.exceptions.filter(is_skipped=True).count()
                count = count + skipped_count

            occurrences = rrule(
                freq=freq_map[str(series.frequency)],
                interval=series.interval,  # type: ignore[arg-type]
                dtstart=series.start_date,
                until=series.until or to_date,
                count=count,
            )
            return [dt.date() for dt in occurrences]

    @classmethod
    def _calculate_smart_amount(
        cls, series: BudgetSeries, use_smart_amount: bool = False
    ) -> float:
        """Calculate smart budget amount based on historical spending.

        If this is the 7th+ occurrence (6+ previous budgets exist), calculate
        the average spending from the last 6 budgets in the series currency.
        Otherwise, use the series amount.

        Args:
            series: The BudgetSeries to calculate amount for
            use_smart_amount: If False, always return series.amount (faster)

        Returns:
            Smart amount based on historical data or series default
        """
        # Fast path: skip expensive calculation if not needed
        if not use_smart_amount:
            return float(series.amount)
        # Get existing budgets for this series, ordered by date
        existing_budgets = (
            Budget.objects.filter(series=series)
            .select_related("currency")
            .prefetch_related("transaction_set__multicurrency")
            .order_by("-budget_date")[:6]
        )

        if existing_budgets.count() < 6:
            return float(series.amount)

        currency_code = series.currency.code
        total_spending = 0.0
        budgets_with_spending = 0

        for budget in existing_budgets:
            # Sum all transaction amounts in the budget's currency
            budget_spending = 0.0
            # Use prefetched transactions instead of fresh query
            transactions = budget.transaction_set.all()

            for transaction in transactions:
                # Get amount from multicurrency conversion
                if hasattr(transaction, "multicurrency") and transaction.multicurrency:
                    amount_map = transaction.multicurrency.amount_map
                    budget_spending += amount_map.get(currency_code, 0.0)
                else:
                    # Fallback: if no multicurrency, check if same currency
                    if transaction.currency.code == currency_code:
                        budget_spending += transaction.amount

            # Only include budgets with actual spending
            if budget_spending > 0:
                total_spending += budget_spending
                budgets_with_spending += 1

        if budgets_with_spending > 0:
            average_spending = total_spending / budgets_with_spending
            logger.debug(
                "smart_amount.calculated",
                series=series.title,
                average=average_spending,
                budgets_with_spending=budgets_with_spending,
                currency=currency_code,
            )
            return average_spending

        # In case if all budgets are with zero spending, return series amount
        return float(series.amount)

    @classmethod
    # TODO: Need to consider 'workspace' parameter usage
    # maybe it make sense to allow materialization per workspace permission
    # like admin can materialize for all workspace budgets
    # member only for his own budgets
    def materialize_budgets(
        cls,
        workspace: Workspace,
        date_to: datetime.datetime,
    ) -> None:
        now = datetime.datetime.now()
        logger.info(
            "materialize_budgets.started",
            workspace_id=workspace.uuid,
            date_to=date_to.isoformat(),
        )
        db_query_count = 0

        # Prefetch exceptions to avoid N+1 queries (1 query instead of 72)
        # Only fetch active series (no until date or until date in the future)
        logger.debug("materialize_budgets.fetching_series")
        series_list = (
            BudgetSeries.objects.filter(workspace=workspace)
            .filter(Q(until__isnull=True) | Q(until__gte=date_to.date()))
            .prefetch_related("exceptions")
        )
        db_query_count += 1  # 1 query for series + prefetch_related
        logger.info(
            "materialize_budgets.series_fetched",
            series_count=len(series_list),
            db_queries=db_query_count,
        )

        # Collect all dates we'll need to check across all series
        all_budget_lookups = []
        series_dates_map = {}  # Map series to their dates for later processing

        for series in series_list:
            dates = cls._calculate_occurrences(series, date_to)
            skipped_dates = set(
                series.exceptions.filter(is_skipped=True).values_list("date", flat=True)
            )

            valid_dates = [date for date in dates if date not in skipped_dates]
            series_dates_map[series.uuid] = valid_dates

            for date in valid_dates:
                all_budget_lookups.append((series.title, date, series.user_id))

        # Bulk fetch all existing budgets in one query
        existing_budgets = {}
        if all_budget_lookups:
            titles = {lookup[0] for lookup in all_budget_lookups}
            dates = {lookup[1] for lookup in all_budget_lookups}
            user_ids = {lookup[2] for lookup in all_budget_lookups}

            logger.debug(
                "materialize_budgets.fetching_existing_budgets",
                budget_lookups_count=len(all_budget_lookups),
            )
            budgets_qs = Budget.objects.filter(
                title__in=titles,
                budget_date__in=dates,
                user_id__in=user_ids,
            ).select_related("series")
            db_query_count += 1  # 1 query for existing budgets

            for budget in budgets_qs:
                key = (budget.title, budget.budget_date, budget.user_id)
                existing_budgets[key] = budget

            logger.info(
                "materialize_budgets.existing_budgets_fetched",
                existing_count=len(existing_budgets),
                db_queries=db_query_count,
            )

        # Process each series and collect operations
        budgets_to_create = []
        budgets_to_update = []
        new_budget_uuids_pending = []

        for series in series_list:
            logger.info("materialize_budgets.processing_series", series=series.title)

            valid_dates = series_dates_map[series.uuid]

            # Use series amount directly for performance
            # Smart amount calculation is expensive (requires transaction queries)
            # and not critical for materialization
            smart_amount = float(series.amount)

            for date in valid_dates:
                key = (series.title, date, series.user_id)
                existing_budget = existing_budgets.get(key)

                if existing_budget is None:
                    # Create new budget
                    new_budget = Budget(
                        title=series.title,
                        budget_date=date,
                        user=series.user,
                        workspace=series.workspace,
                        amount=smart_amount,
                        category=series.category,
                        currency=series.currency,
                        series=series,
                    )
                    budgets_to_create.append(new_budget)
                    logger.debug(
                        "materialize_budgets.will_create",
                        budget=series.title,
                        date=date,
                        amount=smart_amount,
                    )
                elif not existing_budget.series:
                    # Budget exists but has no series - link it to this series
                    existing_budget.series = series
                    budgets_to_update.append(existing_budget)
                    logger.debug(
                        "materialize_budgets.will_link",
                        budget=series.title,
                        date=date,
                        budget_uuid=existing_budget.uuid,
                        series_uuid=series.uuid,
                    )

        # Bulk create new budgets
        if budgets_to_create:
            # Store UUIDs before bulk_create since ignore_conflicts returns empty list
            pending_uuids = [budget.uuid for budget in budgets_to_create]

            # Use ignore_conflicts to skip budgets that already exist
            # (race condition or concurrent materialization)
            logger.debug(
                "materialize_budgets.creating_budgets",
                count=len(budgets_to_create),
            )
            Budget.objects.bulk_create(budgets_to_create, ignore_conflicts=True)
            db_query_count += 1  # 1 query for bulk create

            # Verify which budgets were actually created
            logger.debug("materialize_budgets.verifying_created_budgets")
            new_budget_uuids_pending = list(
                Budget.objects.filter(uuid__in=pending_uuids).values_list(
                    "uuid", flat=True
                )
            )
            db_query_count += 1  # 1 query for verification

            logger.info(
                "materialize_budgets.bulk_created",
                created=len(new_budget_uuids_pending),
                attempted=len(budgets_to_create),
                conflicts=len(budgets_to_create) - len(new_budget_uuids_pending),
                db_queries=db_query_count,
            )

        # Bulk update budgets that need series linked
        if budgets_to_update:
            logger.debug(
                "materialize_budgets.updating_budgets",
                count=len(budgets_to_update),
            )
            Budget.objects.bulk_update(budgets_to_update, ["series"])
            db_query_count += 1  # 1 query for bulk update
            logger.info(
                "materialize_budgets.bulk_updated",
                count=len(budgets_to_update),
                db_queries=db_query_count,
            )

        # Bulk create multicurrency amounts for new budgets
        if new_budget_uuids_pending:
            logger.debug(
                "materialize_budgets.creating_multicurrency",
                budget_count=len(new_budget_uuids_pending),
            )
            # Note: create_budget_multicurrency_amount will add its own DB queries
            cls.create_budget_multicurrency_amount(
                new_budget_uuids_pending, workspace=workspace
            )
            # Multicurrency creation typically involves: 1 query for rates, 1 for bulk create
            db_query_count += 2

        logger.info(
            "materialize_budgets.completed",
            total_db_queries=db_query_count,
            series_processed=len(series_list),
            budgets_created=len(budgets_to_create) if budgets_to_create else 0,
            budgets_updated=len(budgets_to_update) if budgets_to_update else 0,
            multicurrency_created=len(new_budget_uuids_pending)
            if new_budget_uuids_pending
            else 0,
            time_taken=(datetime.datetime.now() - now).total_seconds(),
        )

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
        date_to_formatted = utils.get_end_of_current_week_datetime(date_to)
        cls.materialize_budgets(workspace, date_to_formatted)
        budgets = (
            budgets_qs.filter(budget_date__lte=date_to, budget_date__gte=date_from)
            .select_related("currency", "category", "multicurrency", "user", "series")
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
                recurrent=budget.recurrent_type,
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
                        "recurrent": item.recurrent_type,  # Use property instead of database field
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
