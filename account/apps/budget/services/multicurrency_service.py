"""Budget Multicurrency Service.

Handles multi-currency operations for budgets, including currency conversion
and rate lookups.
"""

from uuid import UUID

from budget.models import Budget, BudgetMulticurrency
from currencies.models import Currency
from rates.models import Rate
from rates.utils import generate_amount_map
from workspaces.models import Workspace


class BudgetMulticurrencyService:
    """Service for handling budget multi-currency operations."""

    @classmethod
    def create_budget_multicurrency_amount(
        cls, uuids: list[UUID], workspace: Workspace
    ) -> None:
        """Create or update multicurrency amounts for budgets.

        Args:
            uuids: List of budget UUIDs to process
            workspace: Workspace to get base currency from

        Creates BudgetMulticurrency records with converted amounts in all
        workspace currencies using the exchange rates for the budget date.
        """
        budgets = Budget.objects.select_related("currency").filter(uuid__in=uuids)
        dates = budgets.values_list("budget_date", flat=True).distinct()
        rates_on_date = Rate.objects.filter(rate_date__in=dates)
        for budget in budgets:
            amount_map = generate_amount_map(budget, rates_on_date, workspace=workspace)

            BudgetMulticurrency.objects.update_or_create(
                budget=budget, defaults={"amount_map": amount_map}
            )

    @classmethod
    def _get_latest_rates(cls) -> dict[str, float]:
        """Get the latest exchange rate for each currency.

        Returns:
            Dict mapping currency code to latest rate value
        """
        latest_rates = {}
        for currency in Currency.objects.all():
            rate = Rate.objects.filter(currency=currency).order_by("-rate_date").first()
            if rate:
                latest_rates[currency.code] = rate.rate
        return latest_rates
