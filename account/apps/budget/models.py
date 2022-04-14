from django.db import models
import uuid


class Budget(models.Model):
    uuid = models.UUIDField(unique=True, default=uuid.uuid4, editable=False)
    category = models.ForeignKey(
        "categories.Category", on_delete=models.CASCADE, to_field="uuid"
    )
    title = models.CharField(max_length=60)
    amount = models.IntegerField()
    budget_date = models.DateField()
    description = models.CharField(max_length=255, blank=True)
    is_completed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)
