import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _

from users.models import User


class Workspace(models.Model):
    uuid = models.UUIDField(unique=True, default=uuid.uuid4, editable=False)
    name = models.CharField(_("name"), max_length=255)
    owner = models.ForeignKey(
        User, related_name="workspace_owner", on_delete=models.CASCADE
    )
    members = models.ManyToManyField(
        User, related_name="workspaces", null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name
