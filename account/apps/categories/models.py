import uuid

from django.db import models
from django.db.models import Q

from categories import constants


class Category(models.Model):
    uuid = models.UUIDField(unique=True, default=uuid.uuid4, editable=False)
    icon = models.CharField(max_length=4, blank=True, null=True)
    name = models.CharField(max_length=128)
    parent = models.ForeignKey(
        "self",
        related_name="categories",
        blank=True,
        null=True,
        on_delete=models.CASCADE,
        to_field="uuid",
    )
    workspace = models.ForeignKey(
        "workspaces.Workspace", to_field="uuid", on_delete=models.DO_NOTHING
    )
    type = models.CharField(
        max_length=3, choices=constants.CATEGORY_TYPES, default=constants.EXPENSE
    )
    description = models.CharField(max_length=255, blank=True)
    position = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                name="unique_name_per_parent",
                fields=["name", "parent"],
            ),
            models.UniqueConstraint(
                name="unique_position_per_parent",
                fields=["parent", "position"],
            ),
        ]
        ordering = ["position"]
        indexes = [
            models.Index(fields=["parent", "position"]),
        ]

    def __str__(self):
        return str(self.name)
