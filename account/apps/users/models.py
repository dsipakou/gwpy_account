import uuid

from currencies.models import Currency
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    uuid = models.UUIDField(unique=True, default=uuid.uuid4, editable=False)
    default_currency = models.ForeignKey(
        Currency, on_delete=models.DO_NOTHING, to_field="uuid", null=True
    )
