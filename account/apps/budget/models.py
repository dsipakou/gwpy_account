import uuid

from django.db import models

from budget.constants import BudgetDuplicateType


class Budget(models.Model):
    RECURRENT_CHOICES = (
        (BudgetDuplicateType.WEEKLY.value, "Weekly"),
        (BudgetDuplicateType.MONTHLY.value, "Monthly"),
    )

    uuid = models.UUIDField(unique=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey("users.User", on_delete=models.DO_NOTHING, to_field="uuid")
    workspace = models.ForeignKey(
        "workspaces.Workspace", to_field="uuid", on_delete=models.DO_NOTHING
    )
    category = models.ForeignKey(
        "categories.Category", on_delete=models.CASCADE, to_field="uuid"
    )
    currency = models.ForeignKey(
        "currencies.Currency", on_delete=models.DO_NOTHING, to_field="uuid"
    )
    title = models.CharField(max_length=60)
    amount = models.FloatField()
    budget_date = models.DateField(blank=True, null=True)
    description = models.TextField(null=True, blank=True)
    is_completed = models.BooleanField(default=False)
    recurrent = models.CharField(
        null=True, blank=True, max_length=20, choices=RECURRENT_CHOICES
    )
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)

    def __repr__(self) -> str:
        return f"({self.title} / {self.budget_date} / {self.currency.code})"

    @property
    def multicurrency_map(self):
        return (
            self.multicurrency.amount_map
            if hasattr(self, "multicurrency") and self.multicurrency
            else {}
        )

    class Meta:
        unique_together = ["title", "budget_date", "user"]


class BudgetMulticurrency(models.Model):
    uuid = models.UUIDField(unique=True, default=uuid.uuid4, editable=False)
    budget = models.OneToOneField(
        Budget, to_field="uuid", related_name="multicurrency", on_delete=models.CASCADE
    )
    amount_map = models.JSONField(default=dict)
