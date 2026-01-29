"""Budget Duplication Service.

LEGACY: This service handles the old budget duplication system that predates
the BudgetSeries feature. It's maintained for backward compatibility with
existing OCCASIONAL, MONTHLY, and WEEKLY budget duplication workflows.

Note: New code should use BudgetSeries for recurring budgets instead.
This service will be deprecated once all users migrate to the series system.
"""

import datetime
from typing import TYPE_CHECKING

from dateutil.relativedelta import relativedelta
from django.db.models import FloatField, Q, Sum, Value
from django.db.models.fields.json import KeyTextTransform
from django.db.models.functions import Cast, Coalesce, Round

from budget import utils
from budget.constants import BudgetDuplicateType
from budget.exceptions import UnsupportedDuplicateTypeError
from budget.models import Budget
from budget.services.multicurrency_service import BudgetMulticurrencyService
from transactions.models import Transaction
from workspaces.models import Workspace

if TYPE_CHECKING:
    from django.db.models import QuerySet

# Legacy mapping for budget duplication types
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


class BudgetDuplicationService:
    """Service for legacy budget duplication (pre-BudgetSeries).

    LEGACY: This service supports the old manual budget duplication workflow.
    For new recurring budgets, use BudgetSeries instead.
    """

    @classmethod
    def get_duplicate_candidates(
        cls,
        qs: "QuerySet",
        recurrent_type: BudgetDuplicateType,
        pivot_date: str | None = None,
    ) -> list[dict[str, str | datetime.date | float]]:
        """Find budgets that can be duplicated for the next period.

        Args:
            qs: QuerySet of Budget models to search
            recurrent_type: Type of recurrence (MONTHLY, WEEKLY, OCCASIONAL)
            pivot_date: Optional pivot date for relative date calculations

        Returns:
            List of budget candidate dicts with uuid, date, title, amount, currency

        Raises:
            UnsupportedDuplicateTypeError: If recurrent_type is not supported
        """
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
    def duplicate_budgets(
        cls, budgets: list[dict[str, str | float]], workspace: Workspace
    ) -> None:
        """Duplicate budgets for the next period.

        Args:
            budgets: List of budget dicts with uuid and optional value
            workspace: Workspace for multicurrency conversion

        Creates new budget instances for the next period based on the
        recurrent_type of the source budget.
        """
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
                new_budget = Budget.objects.create(
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

                BudgetMulticurrencyService.create_budget_multicurrency_amount(
                    [new_budget.uuid], workspace=workspace
                )
