import uuid

from django.db import models
from rates.models import Rate


class Transaction(models.Model):
    uuid = models.UUIDField(unique=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey("users.User", on_delete=models.CASCADE, to_field="uuid")
    category = models.ForeignKey(
        "categories.Category", on_delete=models.CASCADE, to_field="uuid"
    )
    budget = models.ForeignKey(
        "budget.Budget", on_delete=models.CASCADE, to_field="uuid", null=True
    )
    currency = models.ForeignKey(
        "currencies.Currency", on_delete=models.CASCADE, to_field="uuid"
    )
    amount = models.FloatField()
    account = models.ForeignKey(
        "accounts.Account", on_delete=models.CASCADE, to_field="uuid"
    )
    description = models.CharField(max_length=255, blank=True)
    transaction_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)

    @property
    def spent_in_base_currency(self):
        if self.currency.is_base:
            return self.amount
        rate = Rate.objects.get(currency=self.currency, rate_date=self.transaction_date)
        return self.amount * rate.rate
