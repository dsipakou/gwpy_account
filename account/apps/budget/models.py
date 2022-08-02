import uuid

from budget.constants import BudgetDuplicateType
from django.db import models


class Budget(models.Model):
    RECURRENT_CHOICES = (
        (BudgetDuplicateType.WEEKLY.value, "Weekly"),
        (BudgetDuplicateType.MONTHLY.value, "Monthly"),
    )

    uuid = models.UUIDField(unique=True, default=uuid.uuid4, editable=False)
    category = models.ForeignKey(
        "categories.Category", on_delete=models.CASCADE, to_field="uuid", null=True
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
