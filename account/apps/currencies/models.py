import uuid

from django.db import models


class Currency(models.Model):
    uuid = models.UUIDField(unique=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=5, unique=True)
    sign = models.CharField(max_length=2)
    verbal_name = models.CharField(max_length=30)
    comments = models.CharField(max_length=255, blank=True)
    workspace = models.ForeignKey(
        "workspaces.Workspace", to_field="uuid", on_delete=models.DO_NOTHING
    )
    is_base = models.BooleanField(default=False)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.code
