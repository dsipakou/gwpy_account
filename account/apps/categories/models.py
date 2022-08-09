import uuid

from categories import constants
from django.db import models
from django.db.models import Q


class Category(models.Model):
    uuid = models.UUIDField(unique=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=128)
    parent = models.ForeignKey(
        "self",
        related_name="categories",
        blank=True,
        null=True,
        on_delete=models.CASCADE,
        to_field="uuid",
    )
    type = models.CharField(
        max_length=3, choices=constants.CATEGORY_TYPES, default=constants.EXPENSE
    )
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ["name", "parent"]
        constraints = [
            models.UniqueConstraint(
                name="name_parent_null_uniq",
                fields=["name"],
                condition=Q(parent=None),
            ),
        ]
