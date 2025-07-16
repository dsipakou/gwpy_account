import csv
import uuid

from accounts.models import Account
from budget.models import Budget
from categories.models import Category
from currencies.models import Currency
from django.core.management.base import BaseCommand
from users.models import User

from transactions.models import Transaction


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("transaction_path", type=str)
        parser.add_argument("first_user", type=str)
        parser.add_argument("second_user", type=str)
        parser.add_argument("default_currency", type=str)

    def handle(self, *args, **kwargs):
        transaction_path = kwargs["transaction_path"]

        currency_map = {
            1: "BYN",
            2: "USD",
            4: "EUR",
            6: "RUB",
            7: "PLN",
            -1: kwargs["default_currency"],
        }

        user_map = {
            "1": kwargs["first_user"],
            "2": kwargs["second_user"],
        }

        Transaction.objects.all().delete()

        with open(transaction_path) as file:
            data = list(csv.reader(file, delimiter=","))
            for row in data[1:]:
                currency_indx = int(row[10]) if row[10] else -1
                Transaction.objects.create(
                    uuid=uuid.uuid4(),
                    user=User.objects.get(uuid=user_map[row[1]]),
                    category=Category.objects.get(orig_pk=row[2]),
                    budget=Budget.objects.get(orig_pk=row[11]) if row[11] else None,
                    currency=Currency.objects.get(code=currency_map[currency_indx]),
                    amount=row[3],
                    account=Account.objects.get(orig_pk=row[4]),
                    description=row[5],
                    transaction_date=row[8],
                    created_at=row[6],
                    modified_at=row[7],
                )
