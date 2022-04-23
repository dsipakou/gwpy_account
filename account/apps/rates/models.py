import uuid

from currencies.models import Currency
from django.db import models


class Rate(models.Model):
    uuid = models.UUIDField(unique=True, default=uuid.uuid4, editable=False)
    currency = models.ForeignKey(Currency, on_delete=models.CASCADE, to_field="uuid")
    rate_date = models.DateField()
    rate = models.FloatField()
    description = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ["currency", "rate_date"]
