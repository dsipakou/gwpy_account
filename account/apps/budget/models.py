import uuid

from budget.constants import BudgetDuplicateType
from currencies.models import Currency
from django.db import models
from transactions.models import Transaction


class Budget(models.Model):
    RECURRENT_CHOICES = (
        (BudgetDuplicateType.WEEKLY.value, "Weekly"),
        (BudgetDuplicateType.MONTHLY.value, "Monthly"),
    )

    uuid = models.UUIDField(unique=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey("users.User", on_delete=models.DO_NOTHING, to_field="uuid")
    category = models.ForeignKey(
        "categories.Category", on_delete=models.CASCADE, to_field="uuid", null=True
    )
    currency = models.ForeignKey(
        "currencies.Currency", on_delete=models.DO_NOTHING, to_field="uuid"
    )
    title = models.CharField(max_length=60)
    amount = models.IntegerField()
    budget_date = models.DateField()
    description = models.CharField(max_length=255, blank=True)
    is_completed = models.BooleanField(default=False)
    recurrent = models.CharField(
        null=True, blank=True, max_length=20, choices=RECURRENT_CHOICES
    )
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)


class BudgetAmount(models.Model):
    uuid = models.UUIDField(unique=True, default=uuid.uuid4, editable=False)
    transaction = models.ForeignKey(
        Transaction, to_field="uuid", on_delete=models.CASCADE
    )
    currency = models.ForeignKey(Currency, to_field="uuid", on_delete=models.DO_NOTHING)
    amount = models.FloatField(default=0)

    class Meta:
        unique_together = ["transaction", "currency"]
