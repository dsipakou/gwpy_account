"""Budget Series Service.

Handles budget series materialization - the process of automatically creating
individual Budget instances from recurring BudgetSeries definitions.
"""

import datetime

import structlog
from dateutil.relativedelta import relativedelta
from dateutil.rrule import MONTHLY, WEEKLY, rrule
from django.db.models import Q

from budget.models import Budget, BudgetSeries
from budget.services.multicurrency_service import BudgetMulticurrencyService
from workspaces.models import Workspace

logger = structlog.get_logger()


class BudgetSeriesService:
    """Service for budget series materialization and management."""

    @classmethod
    def calculate_occurrences(
        cls, series: BudgetSeries, to_date: datetime.date | datetime.datetime
    ) -> list[datetime.date]:
        """Calculate occurrence dates for a budget series.

        Args:
            series: BudgetSeries to calculate occurrences for
            to_date: End date for calculating occurrences

        Returns:
            List of dates when budgets should exist for this series
        """
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
    def calculate_smart_amount(
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
    def materialize_budgets(
        cls,
        workspace: Workspace,
        date_to: datetime.datetime,
    ) -> None:
        """Materialize budget series into individual Budget instances.

        This method:
        1. Fetches active budget series for the workspace
        2. Calculates which dates should have budgets
        3. Bulk creates missing budgets
        4. Links existing budgets to their series
        5. Creates multicurrency conversion amounts

        Args:
            workspace: Workspace to materialize budgets for
            date_to: End date for materialization (inclusive)

        Performance notes:
        - Uses bulk operations to minimize database queries
        - Prefetches related data to avoid N+1 queries
        - Logs query counts and timing for monitoring
        """
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
            dates = cls.calculate_occurrences(series, date_to)
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
            BudgetMulticurrencyService.create_budget_multicurrency_amount(
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
