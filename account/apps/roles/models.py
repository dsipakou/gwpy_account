import uuid

from django.db import models


class Role(models.Model):
    uuid = models.UUIDField(unique=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=128)
    is_system = models.BooleanField(default=False)


class UserRole(models.Model):
    uuid = models.UUIDField(unique=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey("users.User", on_delete=models.CASCADE, to_field="uuid")
    workspace = models.ForeignKey(
        "workspaces.Workspace", to_field="uuid", on_delete=models.CASCADE
    )
    role = models.ForeignKey(Role, on_delete=models.CASCADE, to_field="uuid")

    class Meta:
        unique_together = ["user", "workspace"]
