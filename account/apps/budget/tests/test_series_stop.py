import datetime
import uuid

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import Account
from budget.models import Budget, BudgetSeries
from categories.models import Category
from currencies.models import Currency
from transactions.models import Transaction
from users.models import User
from workspaces.models import Workspace


class TestBudgetSeriesStop(TestCase):
    """Test stopping a budget series with transaction protection"""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            username="stoptest", email="stoptest@test.com", password="testpassword"
        )
        cls.workspace = Workspace.objects.create(
            name="Stop Test Workspace", owner=cls.owner
        )
        cls.owner.active_workspace = cls.workspace
        cls.owner.save()

        cls.currency = Currency.objects.create(
            code="USD", sign="$", is_base=True, workspace=cls.workspace
        )
        cls.category = Category.objects.create(
            uuid=uuid.uuid4(), name="Groceries", workspace=cls.workspace
        )
        cls.account = Account.objects.create(
            uuid=uuid.uuid4(),
            title="Test Account",
            description="Test account",
            is_main=True,
            user=cls.owner,
            workspace=cls.workspace,
            category=cls.category,
        )

    def setUp(self):
        # Clean up before each test
        Budget.objects.all().delete()
        BudgetSeries.objects.all().delete()
        Transaction.objects.all().delete()

        # Set up API client
        self.client = APIClient()
        self.client.force_authenticate(user=self.owner)

    def test_stop_series_with_transaction_protection(self):
        """Test that stopping a series unlinks budgets with transactions instead of deleting them"""
        today = datetime.date(2024, 1, 1)

        # Create a series with 3 budgets: W1, W2, W3
        series = BudgetSeries.objects.create(
            user=self.owner,
            workspace=self.workspace,
            title="Weekly Groceries",
            category=self.category,
            currency=self.currency,
            amount=100.0,
            start_date=today,
            frequency=BudgetSeries.Frequency.WEEKLY,
            interval=1,
        )

        # W1 - budget at start date
        budget_w1 = Budget.objects.create(
            user=self.owner,
            workspace=self.workspace,
            category=self.category,
            currency=self.currency,
            title="Weekly Groceries",
            amount=100.0,
            budget_date=today,
            series=series,
        )

        # W2 - budget one week later WITH transactions
        budget_w2 = Budget.objects.create(
            user=self.owner,
            workspace=self.workspace,
            category=self.category,
            currency=self.currency,
            title="Weekly Groceries",
            amount=100.0,
            budget_date=today + datetime.timedelta(days=7),
            series=series,
        )

        # Add transaction to W2
        transaction_w2 = Transaction.objects.create(
            user=self.owner,
            workspace=self.workspace,
            category=self.category,
            currency=self.currency,
            account=self.account,
            budget=budget_w2,
            amount=50.0,
            transaction_date=today + datetime.timedelta(days=7),
        )

        # W3 - budget two weeks later WITHOUT transactions
        budget_w3 = Budget.objects.create(
            user=self.owner,
            workspace=self.workspace,
            category=self.category,
            currency=self.currency,
            title="Weekly Groceries",
            amount=100.0,
            budget_date=today + datetime.timedelta(days=14),
            series=series,
        )

        # Verify initial state
        self.assertEqual(Budget.objects.count(), 3)
        self.assertEqual(Transaction.objects.count(), 1)

        # Stop series at W1 (pass W2's date to keep W1 and delete W2, W3)
        # The API subtracts 1 day, so passing W2's date means "stop before W2"
        url = f"/budget/series/{budget_w1.uuid}/stop/"
        response = self.client.post(
            url, {"until": (today + datetime.timedelta(days=7)).strftime("%Y-%m-%d")}
        )

        # Verify response
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["deleted_budgets"], 1)  # W3 deleted
        self.assertEqual(response.data["unlinked_budgets"], 1)  # W2 unlinked

        # Verify series was stopped (until date is W2's date - 1 day = W1's date)
        series.refresh_from_db()
        self.assertEqual(series.until, today + datetime.timedelta(days=6))

        # Verify W1 still exists and is in the series
        budget_w1.refresh_from_db()
        self.assertIsNotNone(budget_w1.series)
        self.assertEqual(budget_w1.series.uuid, series.uuid)

        # Verify W2 still exists but is UNLINKED from series
        budget_w2.refresh_from_db()
        self.assertIsNone(budget_w2.series)  # Unlinked from series
        self.assertEqual(budget_w2.title, "Weekly Groceries")
        self.assertEqual(budget_w2.amount, 100.0)

        # Verify transaction still exists and still references W2
        transaction_w2.refresh_from_db()
        self.assertEqual(transaction_w2.budget.uuid, budget_w2.uuid)

        # Verify W3 was DELETED
        self.assertFalse(Budget.objects.filter(uuid=budget_w3.uuid).exists())

        # Verify total budget count: W1 + W2 (W3 deleted)
        self.assertEqual(Budget.objects.count(), 2)

    def test_stop_series_deletes_budgets_without_transactions(self):
        """Test that budgets without transactions are deleted when stopping series"""
        today = datetime.date(2024, 1, 1)

        # Create a series with 3 budgets, none with transactions
        series = BudgetSeries.objects.create(
            user=self.owner,
            workspace=self.workspace,
            title="Weekly Groceries",
            category=self.category,
            currency=self.currency,
            amount=100.0,
            start_date=today,
            frequency=BudgetSeries.Frequency.WEEKLY,
            interval=1,
        )

        budget_w1 = Budget.objects.create(
            user=self.owner,
            workspace=self.workspace,
            category=self.category,
            currency=self.currency,
            title="Weekly Groceries",
            amount=100.0,
            budget_date=today,
            series=series,
        )

        budget_w2 = Budget.objects.create(
            user=self.owner,
            workspace=self.workspace,
            category=self.category,
            currency=self.currency,
            title="Weekly Groceries",
            amount=100.0,
            budget_date=today + datetime.timedelta(days=7),
            series=series,
        )

        budget_w3 = Budget.objects.create(
            user=self.owner,
            workspace=self.workspace,
            category=self.category,
            currency=self.currency,
            title="Weekly Groceries",
            amount=100.0,
            budget_date=today + datetime.timedelta(days=14),
            series=series,
        )

        # Verify initial state
        self.assertEqual(Budget.objects.count(), 3)

        # Stop series at W1 (pass W2's date to keep W1 and delete W2, W3)
        url = f"/budget/series/{budget_w1.uuid}/stop/"
        response = self.client.post(
            url, {"until": (today + datetime.timedelta(days=7)).strftime("%Y-%m-%d")}
        )

        # Verify response
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["deleted_budgets"], 2)  # W2 and W3 deleted
        self.assertEqual(response.data["unlinked_budgets"], 0)  # None unlinked

        # Verify only W1 remains
        self.assertEqual(Budget.objects.count(), 1)
        self.assertTrue(Budget.objects.filter(uuid=budget_w1.uuid).exists())
        self.assertFalse(Budget.objects.filter(uuid=budget_w2.uuid).exists())
        self.assertFalse(Budget.objects.filter(uuid=budget_w3.uuid).exists())

    def test_stop_series_keeps_all_budgets_with_transactions(self):
        """Test that all future budgets with transactions are unlinked but kept"""
        today = datetime.date(2024, 1, 1)

        # Create a series with 3 budgets, all with transactions
        series = BudgetSeries.objects.create(
            user=self.owner,
            workspace=self.workspace,
            title="Weekly Groceries",
            category=self.category,
            currency=self.currency,
            amount=100.0,
            start_date=today,
            frequency=BudgetSeries.Frequency.WEEKLY,
            interval=1,
        )

        budget_w1 = Budget.objects.create(
            user=self.owner,
            workspace=self.workspace,
            category=self.category,
            currency=self.currency,
            title="Weekly Groceries",
            amount=100.0,
            budget_date=today,
            series=series,
        )

        budget_w2 = Budget.objects.create(
            user=self.owner,
            workspace=self.workspace,
            category=self.category,
            currency=self.currency,
            title="Weekly Groceries",
            amount=100.0,
            budget_date=today + datetime.timedelta(days=7),
            series=series,
        )

        Transaction.objects.create(
            user=self.owner,
            workspace=self.workspace,
            category=self.category,
            currency=self.currency,
            account=self.account,
            budget=budget_w2,
            amount=50.0,
            transaction_date=today + datetime.timedelta(days=7),
        )

        budget_w3 = Budget.objects.create(
            user=self.owner,
            workspace=self.workspace,
            category=self.category,
            currency=self.currency,
            title="Weekly Groceries",
            amount=100.0,
            budget_date=today + datetime.timedelta(days=14),
            series=series,
        )

        Transaction.objects.create(
            user=self.owner,
            workspace=self.workspace,
            category=self.category,
            currency=self.currency,
            account=self.account,
            budget=budget_w3,
            amount=75.0,
            transaction_date=today + datetime.timedelta(days=14),
        )

        # Verify initial state
        self.assertEqual(Budget.objects.count(), 3)
        self.assertEqual(Transaction.objects.count(), 2)

        # Stop series at W1 (pass W2's date to keep W1 and delete W2, W3)
        url = f"/budget/series/{budget_w1.uuid}/stop/"
        response = self.client.post(
            url, {"until": (today + datetime.timedelta(days=7)).strftime("%Y-%m-%d")}
        )

        # Verify response
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["deleted_budgets"], 0)  # None deleted
        self.assertEqual(response.data["unlinked_budgets"], 2)  # W2 and W3 unlinked

        # Verify all budgets still exist
        self.assertEqual(Budget.objects.count(), 3)

        # Verify W1 still in series
        budget_w1.refresh_from_db()
        self.assertIsNotNone(budget_w1.series)

        # Verify W2 and W3 are unlinked but exist
        budget_w2.refresh_from_db()
        budget_w3.refresh_from_db()
        self.assertIsNone(budget_w2.series)
        self.assertIsNone(budget_w3.series)

        # Verify all transactions still exist
        self.assertEqual(Transaction.objects.count(), 2)
