import uuid

from budget.constants import BudgetDuplicateType
from django.db import models


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
    budget = models.OneToOneField(Budget, to_field="uuid", on_delete=models.CASCADE)
    amount_map = models.JSONField(default=dict)
