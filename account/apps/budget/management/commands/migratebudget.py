import csv
import uuid

from budget.models import Budget
from categories.models import Category
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("file_path", type=str)

    def handle(self, *args, **kwars):
        file_path = kwars["file_path"]

        Budget.objects.all().delete()

        with open(file_path) as file:
            data = list(csv.reader(file, delimiter=","))
            for row in data[1:]:
                category = None
                if row[9]:
                    category = Category.objects.get(name=row[9])
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
                )
