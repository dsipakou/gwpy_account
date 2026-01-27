import datetime

import structlog
from dateutil.relativedelta import relativedelta
from django.db import transaction
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.generics import (
    GenericAPIView,
    ListAPIView,
    ListCreateAPIView,
    RetrieveUpdateDestroyAPIView,
)
from rest_framework.response import Response

from budget import serializers
from budget.constants import BudgetDuplicateType
from budget.models import Budget, BudgetSeries, BudgetSeriesException
from budget.serializers import DuplicateResponseSerializer
from budget.services import BudgetService
from categories.models import Category
from currencies.models import Currency
from transactions.models import Transaction
from users.filters import FilterByUser
from users.permissions import BaseUserPermission
from workspaces.filters import FilterByWorkspace

logger = structlog.get_logger()


class BudgetList(ListCreateAPIView):
    queryset = Budget.objects.select_related("category", "series").all()
    filter_backends = (FilterByUser, FilterByWorkspace)
    serializer_class = serializers.BudgetSerializer

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        """Check if category is parent category

        Raises:
            ValidationError: when category is not parent category
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if serializer.validated_data["category"].parent is not None:
            raise ValidationError("Only parent categories can be used for budgets.")
        instance = serializer.save()
        headers = self.get_success_headers(serializer.data)
        workspace = request.user.active_workspace

        BudgetService.create_budget_multicurrency_amount(
            [instance.uuid], workspace=workspace
        )

        return Response(
            serializer.data, status=status.HTTP_201_CREATED, headers=headers
        )


class BudgetPendingList(ListAPIView):
    queryset = Budget.objects.filter(budget_date__isnull=True).select_related("series")
    filter_backends = (FilterByUser, FilterByWorkspace)
    serializer_class = serializers.BudgetSerializer


class BudgetDetails(RetrieveUpdateDestroyAPIView):
    queryset = Budget.objects.select_related("series").prefetch_related(
        "transaction_set"
    )
    serializer_class = serializers.BudgetSerializer
    permission_classes = (BaseUserPermission,)
    lookup_field = "uuid"

    @transaction.atomic
    def perform_update(self, serializer):
        """Check if category is parent category and handle series splitting

        When a budget with a series is updated and significant fields change,
        stop the old series and create a new one with updated values.

        Raises:
            ValidationError: when category is not parent category
        """
        # Get the old instance before changes
        old_instance = self.get_object()
        old_series = old_instance.series

        category = serializer.validated_data.get("category")
        if category and category.parent is not None:
            raise ValidationError("Only parent categories can be used for budgets.")

        # Check if significant fields changed for a budget with a series
        if old_series and old_instance.budget_date:
            # Fields that trigger series split
            changed_fields = {}

            # Check amount
            new_amount = serializer.validated_data.get("amount", old_instance.amount)
            if new_amount != old_series.amount:
                changed_fields["amount"] = new_amount

            # Check currency
            new_currency = serializer.validated_data.get(
                "currency", old_instance.currency
            )
            if new_currency.uuid != old_series.currency.uuid:
                changed_fields["currency"] = new_currency

            # Check category
            new_category = serializer.validated_data.get(
                "category", old_instance.category
            )
            if new_category.uuid != old_series.category.uuid:
                changed_fields["category"] = new_category

            # Check title
            new_title = serializer.validated_data.get("title", old_instance.title)
            if new_title != old_series.title:
                changed_fields["title"] = new_title

            # Check recurrent type (maps to frequency)
            new_recurrent = serializer.validated_data.get(
                "recurrent", old_instance.recurrent_type
            )
            frequency_map = {
                BudgetDuplicateType.WEEKLY.value: BudgetSeries.Frequency.WEEKLY,
                BudgetDuplicateType.MONTHLY.value: BudgetSeries.Frequency.MONTHLY,
            }
            new_frequency = frequency_map.get(new_recurrent) if new_recurrent else None

            if new_frequency and new_frequency != old_series.frequency:
                changed_fields["frequency"] = new_frequency

            # If any significant fields changed, split the series
            if changed_fields:
                # Calculate previous occurrence date based on series frequency
                if old_series.frequency == BudgetSeries.Frequency.WEEKLY:
                    delta = relativedelta(weeks=old_series.interval)
                else:  # MONTHLY
                    delta = relativedelta(months=old_series.interval)

                previous_date = old_instance.budget_date - delta

                # Stop old series at previous occurrence
                old_series.until = previous_date
                old_series.save()

                # Create new series with updated values
                new_series = BudgetSeries.objects.create(
                    user=old_instance.user,
                    workspace=old_instance.workspace,
                    title=changed_fields.get("title", old_series.title),
                    category=changed_fields.get("category", old_series.category),
                    currency=changed_fields.get("currency", old_series.currency),
                    amount=changed_fields.get("amount", old_series.amount),
                    start_date=old_instance.budget_date,
                    frequency=changed_fields.get("frequency", old_series.frequency),
                    interval=old_series.interval,
                    count=None,
                    until=None,
                )

                # Update this budget to point to new series
                serializer.validated_data["series"] = new_series

                # Find all future budgets in the old series (from current date forward)
                future_budgets = Budget.objects.filter(
                    series=old_series, budget_date__gte=old_instance.budget_date
                ).prefetch_related("transaction_set")

                reassigned_count = 0
                updated_count = 0
                for future_budget in future_budgets:
                    # Reassign to new series
                    future_budget.series = new_series
                    reassigned_count += 1

                    # Update values only if budget has no transactions (empty budget)
                    if not future_budget.transaction_set.exists():
                        if "amount" in changed_fields:
                            future_budget.amount = changed_fields["amount"]
                        if "currency" in changed_fields:
                            future_budget.currency = changed_fields["currency"]
                        if "category" in changed_fields:
                            future_budget.category = changed_fields["category"]
                        if "title" in changed_fields:
                            future_budget.title = changed_fields["title"]
                        updated_count += 1

                    future_budget.save()

                logger.info(
                    "budget_series.split",
                    old_series_uuid=old_series.uuid,
                    new_series_uuid=new_series.uuid,
                    budget_uuid=old_instance.uuid,
                    budget_date=old_instance.budget_date,
                    stopped_old_at=previous_date,
                    changed_fields=list(changed_fields.keys()),
                    reassigned_budgets=reassigned_count,
                    updated_budgets=updated_count,
                )

        # Create series if budget doesn't have one but recurrent type is set
        elif not old_series and old_instance.budget_date:
            new_recurrent = serializer.validated_data.get("recurrent")

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

                # Get values from validated_data or fall back to old_instance
                new_series = BudgetSeries.objects.create(
                    user=old_instance.user,
                    workspace=old_instance.workspace,
                    title=serializer.validated_data.get("title", old_instance.title),
                    category=serializer.validated_data.get(
                        "category", old_instance.category
                    ),
                    currency=serializer.validated_data.get(
                        "currency", old_instance.currency
                    ),
                    amount=serializer.validated_data.get("amount", old_instance.amount),
                    start_date=old_instance.budget_date,
                    frequency=frequency,
                    interval=1,
                    count=None,
                    until=None,
                )

                # Update this budget to point to new series
                serializer.validated_data["series"] = new_series

                logger.info(
                    "budget_series.created",
                    series_uuid=new_series.uuid,
                    budget_uuid=old_instance.uuid,
                    budget_date=old_instance.budget_date,
                    frequency=frequency,
                )

        instance = serializer.save()
        BudgetService.create_budget_multicurrency_amount(
            [instance.uuid], workspace=instance.workspace
        )

    @transaction.atomic
    def perform_destroy(self, instance):
        """Track deletion in BudgetSeriesException if budget belongs to a series

        When a budget that's part of a series is deleted, create an exception
        record so the materialization service won't recreate it. All budgets
        are treated equally - no special handling for parent/original budgets.
        """
        # Only track if budget has both series and date
        if instance.series and instance.budget_date:
            BudgetSeriesException.objects.get_or_create(
                series=instance.series,
                date=instance.budget_date,
                defaults={"is_skipped": True},
            )
            logger.info(
                "budget_deleted.exception_created",
                budget_uuid=instance.uuid,
                series_uuid=instance.series.uuid,
                date=instance.budget_date,
            )

        instance.delete()


class MonthlyUsageBudgetList(ListAPIView):
    queryset = Budget.objects.all()
    filter_backends = (FilterByUser, FilterByWorkspace)
    serializer_class = serializers.CategoryBudgetV2Serializer

    def list(self, request, *args, **kwargs):
        date_from = request.GET.get("dateFrom", datetime.date.today())
        date_to = request.GET.get("dateTo", datetime.date.today())
        user = request.GET.get("user")
        queryset = self.filter_queryset(self.get_queryset())
        workspace = request.user.active_workspace

        categories = BudgetService.load_budget_v2(
            workspace=workspace,
            budgets_qs=queryset,
            categories_qs=Category.objects.filter(
                workspace=request.user.active_workspace
            ),
            currencies_qs=Currency.objects.filter(
                workspace=request.user.active_workspace
            ),
            transactions_qs=Transaction.objects.prefetch_related("budget").filter(
                workspace=request.user.active_workspace, budget__in=queryset
            ),
            date_from=date_from,
            date_to=date_to,
            user=user,
        )

        serializer = self.get_serializer(categories, many=True)
        logger.info("Monthly usage requested", date_from=date_from, date_to=date_to)
        return Response(serializer.data)


class WeeklyUsageList(ListAPIView):
    queryset = Budget.objects.all()
    filter_backends = (FilterByUser, FilterByWorkspace)
    serializer_class = serializers.BudgetUsageSerializer

    def list(self, request, *args, **kwargs):
        date_from = request.GET.get(
            "dateFrom", datetime.date.today() - datetime.timedelta(days=30)
        )
        date_to = request.GET.get("dateTo", datetime.date.today())
        user = request.GET.get("user")

        budgets = BudgetService.load_weekly_budget(
            self.filter_queryset(self.get_queryset()),
            Currency.objects.filter(workspace=request.user.active_workspace),
            date_from,
            date_to,
            request.user.active_workspace,
            user,
        )

        serializer = self.get_serializer(budgets, many=True)
        return Response(serializer.data)


class UpcomingBudgetList(ListAPIView):
    queryset = Budget.objects.select_related("series").all()
    filter_backends = (FilterByUser, FilterByWorkspace)
    serializer_class = serializers.BudgetSerializer

    def list(self, request, *args, **kwargs):
        queryset = (
            self.filter_queryset(self.get_queryset())
            .filter(budget_date__gte=datetime.date.today(), is_completed=False)
            .order_by("budget_date")
        )
        limit = request.query_params.get("limit", 6)
        serializer = self.get_serializer(queryset[:limit], many=True)
        return Response(serializer.data)


class DuplicateBudgetView(GenericAPIView):
    queryset = Budget.objects.all()
    filter_backends = (FilterByUser, FilterByWorkspace)
    serializer_class = serializers.DuplicateRequestSerializer
    permission_classes = (BaseUserPermission,)

    def get(self, request, *args, **kwargs):
        pivot_date = request.query_params.get("date")
        if (recurrent_type := request.query_params.get("type")) is not None:
            budgets = BudgetService.get_duplicate_budget_candidates(
                self.filter_queryset(self.queryset), recurrent_type, pivot_date
            )
            response_serializer = DuplicateResponseSerializer(data=budgets, many=True)
            response_serializer.is_valid(raise_exception=True)
            return Response(response_serializer.data)
        else:
            return Response(status=status.HTTP_200_OK, data=[])

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        workspace = request.user.active_workspace
        BudgetService.duplicate_budget(serializer.data["budgets"], workspace=workspace)
        return Response(status=status.HTTP_201_CREATED)


class LastMonthsBudgetUsageList(ListAPIView):
    queryset = Budget.objects.all()
    filter_backends = (FilterByUser, FilterByWorkspace)
    serializer_class = serializers.LastMonthsUsageSerializer

    def list(self, request, *args, **kwargs):
        month_request = request.GET.get("month")
        if month_request:
            month = datetime.datetime.strptime(month_request, "%Y-%m-%d").date()
        else:
            month = datetime.date.today()
        user = request.GET.get("user")
        category_uuid = request.GET.get("category")

        if not category_uuid:
            return Response(status=status.HTTP_400_BAD_REQUEST)

        queryset = self.filter_queryset(self.get_queryset())

        grouped_transactions = BudgetService.get_last_months_usage(
            transactions=Transaction.objects.prefetch_related("budget").filter(
                budget__in=queryset
            ),
            month=month,
            user=request.user,
            filter_by_user=user,
            category_uuid=category_uuid,
        )

        serializer = self.get_serializer(instance=grouped_transactions, many=True)

        return Response(serializer.data)


class BudgetSeriesStop(GenericAPIView):
    """Stop a budget series from materializing future budgets"""

    queryset = BudgetSeries.objects.all()
    permission_classes = (BaseUserPermission,)
    lookup_field = "uuid"

    @transaction.atomic
    def post(self, request, uuid):
        """Stop the series at a specified date or today

        Request body (optional):
        {
            "until": "2024-12-31"  # Stop series at this date (optional, defaults to today)
        }
        """
        try:
            series = self.get_queryset().get(uuid=uuid)
        except BudgetSeries.DoesNotExist:
            return Response(
                {"error": "Series not found"}, status=status.HTTP_404_NOT_FOUND
            )

        # Get until date from request or use today
        until_date_str = request.data.get("until")
        if until_date_str:
            try:
                until_date = datetime.datetime.strptime(
                    until_date_str, "%Y-%m-%d"
                ).date()
            except ValueError:
                return Response(
                    {"error": "Invalid date format. Use YYYY-MM-DD"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        else:
            # Default to today
            until_date = datetime.date.today()

        # Validate: until date should not be before start_date
        if until_date < series.start_date:
            return Response(
                {
                    "error": f"until date cannot be before series start_date ({series.start_date})"
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Delete empty budgets (without transactions) after the until_date
        future_budgets = Budget.objects.filter(
            series=series, budget_date__gt=until_date
        ).prefetch_related("transaction_set")

        deleted_count = 0
        for budget in future_budgets:
            # Only delete if budget has no transactions
            if not budget.transaction_set.exists():
                budget.delete()
                deleted_count += 1

        # Update series
        series.until = until_date
        series.save()

        logger.info(
            "budget_series.stopped",
            series_uuid=series.uuid,
            series_title=series.title,
            until=until_date,
            stopped_by=request.user.uuid,
            deleted_empty_budgets=deleted_count,
        )

        return Response(
            {
                "uuid": series.uuid,
                "title": series.title,
                "until": until_date,
                "deleted_empty_budgets": deleted_count,
                "message": f"Series will stop materializing budgets after {until_date}",
            }
        )
