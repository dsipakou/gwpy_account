import csv
import uuid

from budget.models import Budget
from categories.models import Category
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("budget_path", type=str)
        parser.add_argument("category_path", type=str)

    def handle(self, *args, **kwars):
        budget_path = kwars["budget_path"]
        category_path = kwars["category_path"]

        category_map = {}
        with open(category_path) as file:
            data = list(csv.reader(file, delimiter=","))
            for row in data[1:]:
                category_map[row[0]] = [row[1], row[2]]

        Budget.objects.all().delete()

        with open(budget_path) as file:
            data = list(csv.reader(file, delimiter=","))
            for row in data[1:]:
                category = None
                if row[8]:
                    category_item = category_map[row[8]]
                    parent = None if not category_item[1] else category_item[1]
                    category = Category.objects.get(
                        name=category_item[0], parent=parent
                    )
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
