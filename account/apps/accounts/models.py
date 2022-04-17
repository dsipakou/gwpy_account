import uuid

from django.db import models


class Account(models.Model):
    uuid = models.UUIDField(unique=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey("users.User", on_delete=models.CASCADE, to_field="uuid")
    source = models.CharField(max_length=30)
    amount = models.FloatField()
    description = models.CharField(max_length=255, blank=True)
    is_main = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)
    orig_pk = models.IntegerField()

    class Meta:
        unique_together = ["user", "source"]
