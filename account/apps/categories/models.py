from django.db import models
import uuid


class Category(models.Model):
    uuid = models.UUIDField(unique=True, default=uuid.uuid4, editable=False)
    name = models.CharField(unique=True, max_length=30)
    parent = models.ForeignKey(
        "self",
        related_name="categories",
        blank=True,
        null=True,
        on_delete=models.CASCADE,
        to_field="uuid",
    )
    is_parent = models.BooleanField(default=False)
    is_system = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)
