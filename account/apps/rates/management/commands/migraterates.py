from django.core.management.base import BaseCommand
import csv
from currencies.models import Currency
from rates.models import Rate
import uuid


CURRENCY_MAP = {2: "USD", 4: "EUR", 6: "RUB", 7: "PLN"}


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("file_path", type=str)

    def handle(self, *args, **kwars):
        file_path = kwars["file_path"]

        with open(file_path) as file:
            data = list(csv.reader(file, delimiter=","))
            for row in data[1:]:
                currency_id = Currency.objects.get(code=CURRENCY_MAP[int(row[1])]).uuid
                Rate.objects.create(
                    uuid=uuid.uuid4(),
                    currency_id=currency_id,
                    rate_date=row[2],
                    rate=row[3],
                    created_at=row[5],
                    modified_at=row[6],
                )
