import csv
import uuid

from django.core.management.base import BaseCommand

from accounts.models import Account
from users.models import User


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("file_path", type=str)
        parser.add_argument("first_user", type=str)
        parser.add_argument("second_user", type=str)

    def handle(self, *args, **kwars):
        file_path = kwars["file_path"]

        user_map = {
            "1": kwars["first_user"],
            "2": kwars["second_user"],
        }

        Account.objects.all().delete()

        with open(file_path) as file:
            data = list(csv.reader(file, delimiter=","))
            for row in data[1:]:
                Account.objects.create(
                    uuid=uuid.uuid4(),
                    user=User.objects.get(uuid=user_map[row[1]]),
                    source=row[2],
                    amount=float(row[3]),
                    description=row[4],
                    is_main=False if row[7] == "false" else True,
                    created_at=row[5],
                    modified_at=row[6],
                    orig_pk=row[0],
                )
