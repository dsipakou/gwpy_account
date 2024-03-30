import csv
import uuid

from django.core.management.base import BaseCommand

from categories.models import Category


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("file_path", type=str)

    def handle(self, *args, **kwars):
        file_path = kwars["file_path"]

        Category.objects.all().delete()

        with open(file_path) as file:
            data = list(csv.reader(file, delimiter=","))
            for row in data[1:]:
                if not row[2]:
                    Category.objects.create(
                        uuid=uuid.uuid4(),
                        name=row[1],
                        parent=None,
                        type="EXP" if row[6] == "false" else "INC",
                        created_at=row[3],
                        modified_at=row[4],
                        orig_pk=row[0],
                    )
            for row in data[1:]:
                if row[2]:
                    parent = Category.objects.get(name=row[2])
                    Category.objects.create(
                        uuid=uuid.uuid4(),
                        name=row[1],
                        parent=parent,
                        type="EXP" if row[6] == "false" else "INC",
                        created_at=row[3],
                        modified_at=row[4],
                        orig_pk=row[0],
                    )
