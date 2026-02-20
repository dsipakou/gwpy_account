"""Budget Series Service.

Handles budget series materialization - the process of automatically creating
individual Budget instances from recurring BudgetSeries definitions.
"""

import datetime
from typing import TYPE_CHECKING
from uuid import UUID

import structlog
from dateutil.relativedelta import relativedelta
from dateutil.rrule import MONTHLY, WEEKLY, rrule
from django.db.models import Q

from budget.services.multicurrency_service import BudgetMulticurrencyService
from workspaces.models import Workspace

if TYPE_CHECKING:
    from budget.models import Budget, BudgetSeries
else:
    # Import at runtime to avoid circular imports
    from budget.models import Budget, BudgetSeries

logger = structlog.get_logger()


class BudgetSeriesService:
    """Service for budget series materialization and management."""

    @classmethod
    def calculate_occurrences(
        cls, series: "BudgetSeries", to_date: datetime.date | datetime.datetime
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

            occurrences = rrule(
                freq=freq_map[str(series.frequency)],
                interval=series.interval,  # type: ignore[arg-type]
                dtstart=series.start_date,
                until=series.until or to_date,
                count=series.count,
            )
            return [dt.date() for dt in occurrences]

    @classmethod
    def calculate_smart_amount(
        cls, series: "BudgetSeries", use_smart_amount: bool = False
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

    @classmethod
    def update_budget_series(
        cls,
        budget: "Budget",
        validated_data: dict,
    ) -> tuple["BudgetSeries | None", list[UUID] | None]:
        """Handle series updates when budget fields change.

        Cases handled:
        1. Converting to non-recurrent → Stop series, unlink budget
        2. Frequency change (weekly↔monthly) → Stop old, create new
        3. Significant field changes → Split series
        4. Adding recurrence → Create new series

        Args:
            budget: Budget being updated (old instance before changes)
            validated_data: Dict of fields to update from serializer

        Returns:
            New/updated series if created/changed, None if series removed
        """
        from budget.models import Budget, BudgetSeries

        old_series: BudgetSeries | None = budget.series  # type: ignore[assignment]
        old_budget_date: datetime.date | None = budget.budget_date  # type: ignore[assignment]
        new_budget_date: datetime.date | None = validated_data.get("budget_date")

        # Must have a budget_date for series operations
        if not old_budget_date:
            return old_series, None

        # Import here to avoid circular import
        from budget.constants import BudgetDuplicateType

        # Case 1: Handle recurrent changes that require future budget cleanup
        if old_series:
            new_recurrent = validated_data.get("recurrent", budget.recurrent_type)

            # Map recurrent types to frequencies
            frequency_map = {
                BudgetDuplicateType.WEEKLY.value: BudgetSeries.Frequency.WEEKLY,
                BudgetDuplicateType.MONTHLY.value: BudgetSeries.Frequency.MONTHLY,
            }
            new_frequency = frequency_map.get(new_recurrent) if new_recurrent else None

            # Determine if we need to clean up future budgets
            needs_cleanup = False
            cleanup_reason = None

            # Case 1a: Converting to non-recurrent (handles both None and empty string "")
            if not new_recurrent and budget.recurrent_type is not None:
                needs_cleanup = True
                cleanup_reason = "converted_to_non_recurrent"

            # Case 1b: Changing frequency (weekly↔monthly)
            elif new_frequency and new_frequency != old_series.frequency:
                needs_cleanup = True
                cleanup_reason = "frequency_changed"

            # Case 1c: Changing date (month or day compared to current budget, not series start)
            elif new_budget_date and (new_budget_date.month, new_budget_date.day) != (
                old_budget_date.month,
                old_budget_date.day,
            ):
                needs_cleanup = True
                cleanup_reason = "date_changed"

            if needs_cleanup:
                # Calculate previous occurrence date
                previous_date = cls._calculate_previous_occurrence(
                    old_budget_date, old_series.frequency, old_series.interval
                )

                # Clean up FUTURE budgets (excluding the current budget being updated)
                # The current budget will be updated separately by the view
                deleted_count, unlinked_count = cls._cleanup_future_budgets_after(
                    old_series, old_budget_date
                )

                # Stop the series at previous occurrence
                old_series.until = previous_date
                old_series.save()

                # Handle each case differently after cleanup
                if cleanup_reason == "converted_to_non_recurrent":
                    # Just unlink this budget - no new series
                    logger.info(
                        "budget_series.stopped_by_conversion",
                        series_uuid=old_series.uuid,
                        budget_uuid=budget.uuid,
                        budget_date=old_budget_date,
                        stopped_at=previous_date,
                        reason=cleanup_reason,
                        deleted_empty_budgets=deleted_count,
                        unlinked_budgets_with_transactions=unlinked_count,
                    )
                    return None, None

                elif cleanup_reason == "frequency_changed":
                    # Create new series with the new frequency
                    # Use new_budget_date if date also changed, otherwise old_budget_date
                    new_series = cls._create_series_from_budget(
                        budget=budget,
                        validated_data=validated_data,
                        frequency=new_frequency,
                        start_date=new_budget_date
                        if new_budget_date
                        else old_budget_date,
                    )

                    logger.info(
                        "budget_series.frequency_changed",
                        old_series_uuid=old_series.uuid,
                        new_series_uuid=new_series.uuid,
                        budget_uuid=budget.uuid,
                        budget_date=old_budget_date,
                        old_frequency=old_series.frequency,
                        new_frequency=new_frequency,
                        stopped_at=previous_date,
                        deleted_empty_budgets=deleted_count,
                        unlinked_budgets_with_transactions=unlinked_count,
                    )
                    return new_series, None

                elif cleanup_reason == "date_changed":
                    # Create new series with the new date (same frequency)
                    new_series = cls._create_series_from_budget(
                        budget=budget,
                        validated_data=validated_data,
                        frequency=new_frequency
                        if new_frequency
                        else old_series.frequency,  # Keep same frequency
                        start_date=new_budget_date,  # Use new date
                    )

                    logger.info(
                        "budget_series.date_changed",
                        old_series_uuid=old_series.uuid,
                        new_series_uuid=new_series.uuid,
                        budget_uuid=budget.uuid,
                        old_budget_date=old_budget_date,
                        new_budget_date=new_budget_date,
                        frequency=old_series.frequency,
                        stopped_at=previous_date,
                        deleted_empty_budgets=deleted_count,
                        unlinked_budgets_with_transactions=unlinked_count,
                    )
                    return new_series, None

        # Case 1.5: Handle count-only updates (before checking significant changes)
        if old_series and "number_of_repetitions" in validated_data:
            new_count = validated_data["number_of_repetitions"]
            old_count = old_series.count

            # Check if ONLY count changed (no other significant fields)
            temp_changed_fields = cls._detect_significant_changes(
                budget, old_series, validated_data
            )

            if not temp_changed_fields and new_count != old_count:
                # Count-only update - handle without series split
                from datetime import timedelta

                # If reducing count, delete extra budgets beyond new limit
                if new_count is not None and (
                    old_count is None or new_count < old_count
                ):
                    # Calculate which occurrence number this budget is
                    current_occurrence = 0
                    test_date = old_series.start_date
                    while test_date < old_budget_date:
                        current_occurrence += 1
                        if old_series.frequency == "MONTHLY":
                            test_date = old_series.start_date + relativedelta(
                                months=old_series.interval * current_occurrence
                            )
                        else:  # WEEKLY
                            test_date = old_series.start_date + timedelta(
                                days=7 * old_series.interval * current_occurrence
                            )

                    # Calculate the last allowed date based on new count
                    # Count represents total occurrences (budgets + exceptions)
                    if old_series.frequency == "MONTHLY":
                        last_allowed_date = old_series.start_date + relativedelta(
                            months=old_series.interval * (new_count - 1)
                        )
                    else:  # WEEKLY
                        last_allowed_date = old_series.start_date + timedelta(
                            days=7 * old_series.interval * (new_count - 1)
                        )

                    # Delete budgets beyond the new limit
                    future_budgets = Budget.objects.filter(
                        series=old_series, budget_date__gt=last_allowed_date
                    )

                    # Separate budgets with/without transactions
                    budgets_with_txns = []
                    budgets_without_txns = []

                    for b in future_budgets.select_related("series"):
                        if b.transaction_set.exists():
                            budgets_with_txns.append(b)
                        else:
                            budgets_without_txns.append(b)

                    # Delete empty budgets
                    deleted_count = 0
                    if budgets_without_txns:
                        Budget.objects.filter(
                            uuid__in=[b.uuid for b in budgets_without_txns]
                        ).delete()
                        deleted_count = len(budgets_without_txns)

                    # Unlink budgets with transactions
                    unlinked_count = 0
                    if budgets_with_txns:
                        Budget.objects.filter(
                            uuid__in=[b.uuid for b in budgets_with_txns]
                        ).update(series=None)
                        unlinked_count = len(budgets_with_txns)

                    logger.info(
                        "budget_series.count_reduced",
                        series_uuid=old_series.uuid,
                        old_count=old_count,
                        new_count=new_count,
                        last_allowed_date=last_allowed_date,
                        deleted_empty_budgets=deleted_count,
                        unlinked_budgets_with_transactions=unlinked_count,
                    )

                # Update the count on existing series
                old_series.count = new_count
                old_series.save()

                logger.info(
                    "budget_series.count_updated",
                    series_uuid=old_series.uuid,
                    budget_uuid=budget.uuid,
                    old_count=old_count,
                    new_count=new_count,
                )

                return old_series, None

        # Case 2: Check if significant fields changed for a budget with a series
        if old_series and old_budget_date:
            changed_fields = cls._detect_significant_changes(
                budget, old_series, validated_data
            )

            # If any significant fields changed, update series in place
            if changed_fields:
                # Update the series itself with new values
                if "amount" in changed_fields:
                    old_series.amount = changed_fields["amount"]
                if "currency" in changed_fields:
                    old_series.currency = changed_fields["currency"]
                if "category" in changed_fields:
                    old_series.category = changed_fields["category"]
                if "title" in changed_fields:
                    old_series.title = changed_fields["title"]
                if "budget_date" in changed_fields:
                    old_series.start_date = changed_fields["budget_date"]

                old_series.save()

                # Update all future budgets (including current) with new values
                updated_count, updated_uuids = cls._update_future_budgets(
                    series=old_series,
                    from_date=old_budget_date,
                    changed_fields=changed_fields,
                )

                logger.info(
                    "budget_series.updated_in_place",
                    series_uuid=old_series.uuid,
                    budget_uuid=budget.uuid,
                    budget_date=old_budget_date,
                    changed_fields=list(changed_fields.keys()),
                    updated_budgets=updated_count,
                )
                return old_series, updated_uuids

        # Case 3: Create series if budget doesn't have one but recurrent type is set
        if not old_series and old_budget_date:
            new_recurrent = validated_data.get("recurrent")

            # Import here to avoid circular import
            from budget.constants import BudgetDuplicateType

            # Only create series for weekly/monthly recurrent types
            if new_recurrent in (
                BudgetDuplicateType.WEEKLY.value,
                BudgetDuplicateType.MONTHLY.value,
            ):
                frequency_map = {
                    BudgetDuplicateType.WEEKLY.value: BudgetSeries.Frequency.WEEKLY,
                    BudgetDuplicateType.MONTHLY.value: BudgetSeries.Frequency.MONTHLY,
                }
                frequency = frequency_map[new_recurrent]

                new_series = cls._create_series_from_budget(
                    budget=budget,
                    validated_data=validated_data,
                    frequency=frequency,
                    start_date=old_budget_date,
                )

                logger.info(
                    "budget_series.created",
                    series_uuid=new_series.uuid,
                    budget_uuid=budget.uuid,
                    budget_date=old_budget_date,
                    frequency=frequency,
                )
                return new_series, None

        return old_series, None

    @staticmethod
    def _calculate_previous_occurrence(
        current_date: datetime.date,
        frequency: str,
        interval: int,
    ) -> datetime.date:
        """Calculate the previous occurrence date based on frequency.

        Args:
            current_date: Current budget date
            frequency: Series frequency (WEEKLY or MONTHLY)
            interval: Series interval

        Returns:
            Previous occurrence date
        """
        if str(frequency) == "WEEKLY":
            delta = relativedelta(weeks=interval)
        else:  # MONTHLY
            delta = relativedelta(months=interval)

        return current_date - delta

    @staticmethod
    def _cleanup_future_budgets_after(
        series: "BudgetSeries",
        after_date: datetime.date,
    ) -> tuple[int, int]:
        """Clean up future budgets in a series AFTER a specific date (exclusive).

        Budgets WITHOUT transactions are deleted.
        Budgets WITH transactions are unlinked but preserved.

        Args:
            series: Series to clean up
            after_date: Budgets strictly AFTER this date will be cleaned up (exclusive)

        Returns:
            Tuple of (deleted_count, unlinked_count)
        """
        from budget.models import Budget

        future_budgets = Budget.objects.filter(
            series=series, budget_date__gt=after_date
        ).prefetch_related("transaction_set")

        deleted_count = 0
        unlinked_count = 0

        for future_budget in future_budgets:
            # If budget has no transactions, delete it
            if not future_budget.transaction_set.exists():
                future_budget.delete()
                deleted_count += 1
            else:
                # If budget has transactions, unlink it but keep it
                future_budget.series = None
                future_budget.save()
                unlinked_count += 1

        return deleted_count, unlinked_count

    @staticmethod
    def _detect_significant_changes(
        budget: "Budget",
        series: "BudgetSeries",
        validated_data: dict,
    ) -> dict:
        """Detect which significant fields changed that require series split.

        Args:
            budget: Current budget instance
            series: Current series
            validated_data: New values from serializer

        Returns:
            Dict of changed fields and their new values
        """
        from budget.constants import BudgetDuplicateType

        changed_fields = {}

        # Check amount
        new_amount = validated_data.get("amount", budget.amount)
        if new_amount != series.amount:
            changed_fields["amount"] = new_amount

        # Check currency
        new_currency = validated_data.get("currency", budget.currency)
        if new_currency.uuid != series.currency.uuid:
            changed_fields["currency"] = new_currency

        # Check category
        new_category = validated_data.get("category", budget.category)
        if new_category.uuid != series.category.uuid:
            changed_fields["category"] = new_category

        # Check title
        new_title = validated_data.get("title", budget.title)
        if new_title != series.title:
            changed_fields["title"] = new_title

        new_date = validated_data.get("budget_date")
        if new_date != budget.budget_date:
            changed_fields["budget_date"] = new_date

        # Check recurrent type (maps to frequency)
        new_recurrent = validated_data.get("recurrent", budget.recurrent_type)
        frequency_map = {
            BudgetDuplicateType.WEEKLY.value: BudgetSeries.Frequency.WEEKLY,
            BudgetDuplicateType.MONTHLY.value: BudgetSeries.Frequency.MONTHLY,
        }
        new_frequency = frequency_map.get(new_recurrent) if new_recurrent else None

        if new_frequency and new_frequency != series.frequency:
            changed_fields["frequency"] = new_frequency

        return changed_fields

    @staticmethod
    def _create_series_from_budget(
        budget: "Budget",
        validated_data: dict,
        frequency: str,
        start_date: datetime.date,
    ) -> "BudgetSeries":
        """Create a new series from budget data.

        Args:
            budget: Budget to create series from
            validated_data: New values from serializer
            frequency: Series frequency
            start_date: Series start date

        Returns:
            Newly created BudgetSeries
        """
        from budget.models import BudgetSeries

        return BudgetSeries.objects.create(
            user=budget.user,
            workspace=budget.workspace,
            title=validated_data.get("title", budget.title),
            category=validated_data.get("category", budget.category),
            currency=validated_data.get("currency", budget.currency),
            amount=validated_data.get("amount", budget.amount),
            start_date=start_date,
            frequency=frequency,
            interval=1,
            count=validated_data.get("number_of_repetitions"),
            until=None,
        )

    @staticmethod
    def _update_future_budgets(
        series: "BudgetSeries",
        from_date: datetime.date,
        changed_fields: dict,
    ) -> tuple[int, list[UUID]]:
        """Update future budgets (from current date forward) with new values.

        Args:
            series: Series containing the budgets
            from_date: Start date (inclusive) for updates
            changed_fields: Fields that changed and should be updated

        Returns:
            Count of budgets updated
        """
        from budget.models import Budget

        future_budgets = Budget.objects.filter(
            series=series, budget_date__gte=from_date
        ).prefetch_related("transaction_set")

        updated_count = 0
        updated_budget_uuids = []

        for future_budget in future_budgets:
            # Update values only if budget has no transactions (empty budget)
            # to protect financial records integrity
            if "amount" in changed_fields:
                future_budget.amount = changed_fields["amount"]
            if "currency" in changed_fields:
                future_budget.currency = changed_fields["currency"]
            if "category" in changed_fields:
                future_budget.category = changed_fields["category"]
            if "title" in changed_fields:
                future_budget.title = changed_fields["title"]

            future_budget.save()
            updated_count += 1
            updated_budget_uuids.append(future_budget.uuid)

        # Update multicurrency amounts for budgets that had amount or currency changes
        if updated_budget_uuids and (
            "amount" in changed_fields or "currency" in changed_fields
        ):
            BudgetMulticurrencyService.create_budget_multicurrency_amount(
                updated_budget_uuids, workspace=series.workspace
            )
            logger.debug(
                "budget_series.multicurrency_updated",
                series_uuid=series.uuid,
                updated_budgets=len(updated_budget_uuids),
            )

        return updated_count, updated_budget_uuids

    @staticmethod
    def stop_series(
        series: "BudgetSeries",
        until_date: datetime.date,
    ) -> tuple[int, int, int]:
        """Stop a series at specified date.

        Handles future budgets:
        - WITHOUT transactions: deleted
        - WITH transactions: unlinked but preserved

        Args:
            series: Series to stop
            until_date: Date to stop at (inclusive)

        Returns:
            Tuple of (deleted_count, unlinked_count, deleted_exceptions)
        """
        from budget.models import Budget, BudgetSeriesException

        # Handle future budgets after the until_date
        future_budgets = Budget.objects.filter(
            series=series, budget_date__gt=until_date
        ).prefetch_related("transaction_set")

        deleted_count = 0
        unlinked_count = 0

        for future_budget in future_budgets:
            if not future_budget.transaction_set.exists():
                # No transactions - safe to delete
                future_budget.delete()
                deleted_count += 1
            else:
                # Has transactions - unlink from series but keep the budget
                future_budget.series = None
                future_budget.save()
                unlinked_count += 1

        # Ensure until_date is not before start_date

        # Delete all exceptions for dates > until_date
        # (they're no longer relevant since series ends at until_date)
        deleted_exceptions = BudgetSeriesException.objects.filter(
            series=series, date__gt=until_date
        ).delete()[0]

        budgets_count_after_delete = Budget.objects.filter(series=series).count()
        # Delete series entirely if until_date is before or on start_date
        if budgets_count_after_delete == 0 or until_date <= series.start_date:
            logger.info("budget_series.stopped_and_deleted", series_uuid=series.uuid)
            series.delete()
            return deleted_count, unlinked_count, deleted_exceptions

        # Update series
        series.until = until_date
        series.save()

        logger.info(
            "budget_series.stopped",
            series_uuid=series.uuid,
            series_title=series.title,
            until=until_date,
            deleted_budgets=deleted_count,
            unlinked_budgets_with_transactions=unlinked_count,
            deleted_exceptions=deleted_exceptions,
        )

        return deleted_count, unlinked_count, deleted_exceptions

    @staticmethod
    def track_deletion(budget: "Budget") -> None:
        """Track budget deletion as series exception.

        Creates BudgetSeriesException so materialization service
        won't recreate this budget.

        Args:
            budget: Budget being deleted
        """
        if not (budget.series and budget.budget_date):
            return

        from budget.models import BudgetSeriesException

        BudgetSeriesException.objects.get_or_create(
            series=budget.series,
            date=budget.budget_date,
            defaults={"is_skipped": True},
        )

        logger.info(
            "budget_deleted.exception_created",
            budget_uuid=budget.uuid,
            series_uuid=budget.series.uuid,
            date=budget.budget_date,
        )
