import uuid

from currencies.models import Currency
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.translation import gettext_lazy as _


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

    def currency_code(self):
        return self.default_currency.code if self.default_currency else None

    def __str__(self):
        return self.email
