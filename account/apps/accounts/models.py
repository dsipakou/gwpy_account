import uuid

from django.db import models


class Account(models.Model):
    uuid = models.UUIDField(unique=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey("users.User", on_delete=models.CASCADE, to_field="uuid")
    title = models.CharField(max_length=30)
    category = models.ForeignKey(
        "categories.Category", to_field="uuid", null=True, on_delete=models.DO_NOTHING
    )
    description = models.CharField(max_length=255, blank=True)
    is_main = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ["user", "title"]
