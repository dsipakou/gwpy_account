from budget.models import Budget
from budget.services import BudgetService
from currencies.models import Currency
from rates.entities import BatchedRateRequest
from rates.models import Rate
from transactions.models import Transaction
from transactions.services import TransactionService
from users.models import User
from workspaces.models import Workspace


class RateService:
    @classmethod
    def create_batched_rates(cls, data: BatchedRateRequest):
        user = User.objects.get(uuid=data["user"])
        for item in data["items"]:
            Rate.objects.update_or_create(
                currency_id=item["currency"],
                rate_date=data["rate_date"],
                workspace=user.active_workspace,
                defaults={
                    "rate": item["rate"],
                    "base_currency_id": data["base_currency"],
                },
            )
        # Update budgets only from users workspace
        budget_uuids = Budget.objects.filter(
            budget_date=data["rate_date"], workspace=user.active_workspace
        ).values_list("uuid", flat=True)
        # Update transactions only from users workspace
        transaction_uuids = Transaction.objects.filter(
            transaction_date=data["rate_date"], workspace=user.active_workspace
        ).values_list("uuid", flat=True)
        BudgetService.create_budget_multicurrency_amount(
            budget_uuids, workspace=user.active_workspace
        )
        TransactionService.create_transaction_multicurrency_amount(
            transaction_uuids, workspace=user.active_workspace
        )
