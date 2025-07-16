import csv
import uuid

from categories.models import Category
from django.core.management.base import BaseCommand

from budget.models import Budget


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("budget_path", type=str)

    def handle(self, *args, **kwars):
        budget_path = kwars["budget_path"]

        with open(budget_path) as file:
            data = list(csv.reader(file, delimiter=","))
            for row in data[1:]:
                category = None
                if row[8]:
                    category = Category.objects.get(orig_pk=row[8])
                Budget.objects.create(
                    uuid=uuid.uuid4(),
                    category=category,
                    title=row[1],
                    amount=float(row[2]),
                    budget_date=row[3],
                    description=row[4],
                    is_completed=False if row[7] == "false" else True,
                    created_at=row[5],
                    modified_at=row[6],
                    orig_pk=row[0],
                )
