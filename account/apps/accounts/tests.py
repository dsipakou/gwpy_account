import uuid

from django.test import TestCase
from rest_framework.test import APIClient

from accounts import constants
from accounts.models import Account
from categories.models import Category
from currencies.models import Currency
from users.models import User
from workspaces.models import Workspace


class AccountKindTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="account-user",
            email="account@example.com",
            password="testpassword",
        )
        cls.workspace = Workspace.objects.create(name="Accounts", owner=cls.user)
        cls.user.active_workspace = cls.workspace
        cls.user.save(update_fields=("active_workspace",))

        cls.currency = Currency.objects.create(
            code="USD",
            sign="$",
            verbal_name="US Dollar",
            is_base=True,
            is_default=True,
            workspace=cls.workspace,
        )
        cls.user.default_currency = cls.currency
        cls.user.save(update_fields=("default_currency",))

        cls.category = Category.objects.create(
            uuid=uuid.uuid4(),
            name="Accounts Category",
            workspace=cls.workspace,
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_account_defaults_to_spending_kind(self):
        account = Account.objects.create(
            uuid=uuid.uuid4(),
            title="Checking",
            user=self.user,
            workspace=self.workspace,
            category=self.category,
        )

        self.assertEqual(account.kind, constants.SPENDING)

    def test_account_can_be_created_as_savings(self):
        account = Account.objects.create(
            uuid=uuid.uuid4(),
            title="Emergency Fund",
            kind=constants.SAVINGS,
            user=self.user,
            workspace=self.workspace,
            category=self.category,
        )

        self.assertEqual(account.kind, constants.SAVINGS)

    def test_account_detail_api_returns_kind(self):
        account = Account.objects.create(
            uuid=uuid.uuid4(),
            title="Vacation Fund",
            kind=constants.SAVINGS,
            user=self.user,
            workspace=self.workspace,
            category=self.category,
        )

        response = self.client.get(f"/accounts/{account.uuid}/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["kind"], constants.SAVINGS)

    def test_savings_account_detail_api_returns_empty_usage(self):
        account = Account.objects.create(
            uuid=uuid.uuid4(),
            title="Rainy Day",
            kind=constants.SAVINGS,
            user=self.user,
            workspace=self.workspace,
            category=self.category,
        )

        response = self.client.get(f"/accounts/{account.uuid}/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["usage"], [])
