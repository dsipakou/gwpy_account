import uuid

from django.db import models

from currencies.models import Currency


class Rate(models.Model):
    uuid = models.UUIDField(unique=True, default=uuid.uuid4, editable=False)
    currency = models.ForeignKey(
        Currency, related_name="rates", on_delete=models.CASCADE, to_field="uuid"
    )
    rate_date = models.DateField()
    rate = models.FloatField()
    workspace = models.ForeignKey(
        "workspaces.Workspace", to_field="uuid", on_delete=models.DO_NOTHING
    )
    description = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)
    base_currency = models.ForeignKey(
        Currency,
        to_field="uuid",
        on_delete=models.DO_NOTHING,
        related_name="base_currency",
    )

    class Meta:
        unique_together = ["currency", "rate_date", "workspace"]
