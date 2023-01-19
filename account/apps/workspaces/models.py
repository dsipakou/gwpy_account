from django.db import models
from django.utils.translation import gettext_lazy as _
from users.models import User


class Workspace(models.Model):
    name = models.CharField(_("name"), max_length=255)
    owner = models.ForeignKey(
        User, related_name="owned_workspace", on_delete=models.CASCADE
    )
    members = models.ManyToManyField(User, related_name="workspaces")
