import uuid

from currencies.models import Currency
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.translation import gettext_lazy as _
from roles.constants import Roles
from roles.models import UserRole


class User(AbstractUser):
    uuid = models.UUIDField(unique=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(_("email address"), unique=True)
    first_name = models.CharField(
        _("first name"), max_length=150, blank=True, null=True
    )
    last_name = models.CharField(_("last name"), max_length=150, blank=True, null=True)
    default_currency = models.ForeignKey(
        Currency, on_delete=models.DO_NOTHING, to_field="uuid", null=True
    )
    username = models.CharField(
        _("username"),
        max_length=150,
        help_text=_(
            "Optional. 150 characters or fewer. Letters, digits and @/./+/-/_ only."
        ),
        blank=True,
        null=True,
    )
    active_workspace = models.ForeignKey(
        "workspaces.Workspace", to_field="uuid", on_delete=models.DO_NOTHING, null=True
    )

    def currency_code(self):
        return self.default_currency.code if self.default_currency else None

    def is_owner(self, workspace):
        return workspace.owner == self

    def is_admin(self, workspace):
        user_role = UserRole.objects.filter(user=self, workspace=workspace).first()
        return user_role and user_role.role.name == Roles.ADMIN

    def is_member(self, workspace):
        user_role = UserRole.objects.filter(user=self, workspace=workspace).first()
        return user_role and user_role.role.name == Roles.MEMBER

    def __str__(self):
        return self.email


class Invite(models.Model):
    uuid = models.UUIDField(unique=True, default=uuid.uuid4, editable=False)
    invite_reciever = models.ForeignKey(
        User, to_field="email", on_delete=models.DO_NOTHING, related_name="reciever"
    )
    invite_owner = models.ForeignKey(
        User, to_field="email", on_delete=models.DO_NOTHING, related_name="owner"
    )
    workspace = models.ForeignKey(
        "workspaces.Workspace", to_field="uuid", on_delete=models.DO_NOTHING
    )
    is_accepted = models.BooleanField(default=False)

    class Meta:
        unique_together = ["invite_owner", "invite_reciever", "workspace"]
