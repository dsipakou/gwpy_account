"""Tests for BudgetSeriesService business logic.

Tests the service layer methods that were extracted from views:
- update_budget_series() - Handle series updates/splits
- stop_series() - Stop series with transaction protection
- track_deletion() - Create exception when budget deleted
"""

import datetime
import uuid

from django.test import TestCase

from accounts.models import Account
from budget.constants import BudgetDuplicateType
from budget.models import Budget, BudgetSeries, BudgetSeriesException
from budget.services.series_service import BudgetSeriesService
from categories.models import Category
from currencies.models import Currency
from transactions.models import Transaction
from users.models import User
from workspaces.models import Workspace


class TestBudgetSeriesServiceUpdate(TestCase):
    """Test BudgetSeriesService.update_budget_series() method"""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            username="servicetest",
            email="servicetest@test.com",
            password="testpassword",
        )
        cls.workspace = Workspace.objects.create(
            name="Service Test Workspace", owner=cls.owner
        )
        cls.owner.active_workspace = cls.workspace
        cls.owner.save()

        cls.currency_usd = Currency.objects.create(
            code="USD", sign="$", is_base=True, workspace=cls.workspace
        )
        cls.currency_eur = Currency.objects.create(
            code="EUR", sign="€", is_base=False, workspace=cls.workspace
        )
        cls.category_groceries = Category.objects.create(
            uuid=uuid.uuid4(), name="Groceries", workspace=cls.workspace
        )
        cls.category_transport = Category.objects.create(
            uuid=uuid.uuid4(), name="Transport", workspace=cls.workspace
        )
        cls.account = Account.objects.create(
            uuid=uuid.uuid4(),
            title="Test Account",
            description="Test account",
            is_main=True,
            user=cls.owner,
            workspace=cls.workspace,
            category=cls.category_groceries,
        )

    def setUp(self):
        # Clean up before each test
        Budget.objects.all().delete()
        BudgetSeries.objects.all().delete()
        Transaction.objects.all().delete()
        BudgetSeriesException.objects.all().delete()

    def test_convert_to_non_recurrent_without_transactions(self):
        """Test converting recurrent budget to non-recurrent deletes future budgets"""
        today = datetime.date(2024, 1, 1)

        # Create a weekly series with 3 budgets
        series = BudgetSeries.objects.create(
            user=self.owner,
            workspace=self.workspace,
            title="Weekly Groceries",
            category=self.category_groceries,
            currency=self.currency_usd,
            amount=100.0,
            start_date=today,
            frequency=BudgetSeries.Frequency.WEEKLY,
            interval=1,
        )

        budget_w1 = Budget.objects.create(
            user=self.owner,
            workspace=self.workspace,
            category=self.category_groceries,
            currency=self.currency_usd,
            title="Weekly Groceries",
            amount=100.0,
            budget_date=today,
            series=series,
        )

        # Future budget without transactions
        Budget.objects.create(
            user=self.owner,
            workspace=self.workspace,
            category=self.category_groceries,
            currency=self.currency_usd,
            title="Weekly Groceries",
            amount=100.0,
            budget_date=today + datetime.timedelta(days=7),
            series=series,
        )

        self.assertEqual(Budget.objects.count(), 2)

        # Convert to non-recurrent
        validated_data = {"recurrent": None}
        new_series = BudgetSeriesService.update_budget_series(budget_w1, validated_data)

        # Should return None (no series)
        self.assertIsNone(new_series)

        # Future budget should be deleted
        self.assertEqual(Budget.objects.count(), 1)

        # Series should be stopped
        series.refresh_from_db()
        self.assertIsNotNone(series.until)

    def test_convert_to_non_recurrent_with_transactions(self):
        """Test converting to non-recurrent unlinks budgets with transactions"""
        today = datetime.date(2024, 1, 1)

        series = BudgetSeries.objects.create(
            user=self.owner,
            workspace=self.workspace,
            title="Weekly Groceries",
            category=self.category_groceries,
            currency=self.currency_usd,
            amount=100.0,
            start_date=today,
            frequency=BudgetSeries.Frequency.WEEKLY,
            interval=1,
        )

        budget_w1 = Budget.objects.create(
            user=self.owner,
            workspace=self.workspace,
            category=self.category_groceries,
            currency=self.currency_usd,
            title="Weekly Groceries",
            amount=100.0,
            budget_date=today,
            series=series,
        )

        # Future budget WITH transactions
        budget_w2 = Budget.objects.create(
            user=self.owner,
            workspace=self.workspace,
            category=self.category_groceries,
            currency=self.currency_usd,
            title="Weekly Groceries",
            amount=100.0,
            budget_date=today + datetime.timedelta(days=7),
            series=series,
        )

        Transaction.objects.create(
            user=self.owner,
            workspace=self.workspace,
            category=self.category_groceries,
            currency=self.currency_usd,
            account=self.account,
            budget=budget_w2,
            amount=50.0,
            transaction_date=today + datetime.timedelta(days=7),
        )

        # Convert to non-recurrent
        validated_data = {"recurrent": None}
        new_series = BudgetSeriesService.update_budget_series(budget_w1, validated_data)

        # Should return None
        self.assertIsNone(new_series)

        # Both budgets should still exist
        self.assertEqual(Budget.objects.count(), 2)

        # W2 should be unlinked from series
        budget_w2.refresh_from_db()
        self.assertIsNone(budget_w2.series)

    def test_frequency_change_weekly_to_monthly(self):
        """Test changing frequency from weekly to monthly"""
        today = datetime.date(2024, 1, 1)

        series = BudgetSeries.objects.create(
            user=self.owner,
            workspace=self.workspace,
            title="Groceries",
            category=self.category_groceries,
            currency=self.currency_usd,
            amount=100.0,
            start_date=today,
            frequency=BudgetSeries.Frequency.WEEKLY,
            interval=1,
        )

        budget = Budget.objects.create(
            user=self.owner,
            workspace=self.workspace,
            category=self.category_groceries,
            currency=self.currency_usd,
            title="Groceries",
            amount=100.0,
            budget_date=today,
            series=series,
        )

        # Change to monthly
        validated_data = {"recurrent": BudgetDuplicateType.MONTHLY.value}
        new_series = BudgetSeriesService.update_budget_series(budget, validated_data)

        # Should create new series
        self.assertIsNotNone(new_series)
        self.assertNotEqual(new_series.uuid, series.uuid)
        self.assertEqual(new_series.frequency, BudgetSeries.Frequency.MONTHLY)

        # Old series should be stopped
        series.refresh_from_db()
        self.assertIsNotNone(series.until)

    def test_amount_change_splits_series(self):
        """Test changing amount creates a new series (series split)"""
        today = datetime.date(2024, 1, 1)

        series = BudgetSeries.objects.create(
            user=self.owner,
            workspace=self.workspace,
            title="Groceries",
            category=self.category_groceries,
            currency=self.currency_usd,
            amount=100.0,
            start_date=today,
            frequency=BudgetSeries.Frequency.WEEKLY,
            interval=1,
        )

        budget_w1 = Budget.objects.create(
            user=self.owner,
            workspace=self.workspace,
            category=self.category_groceries,
            currency=self.currency_usd,
            title="Groceries",
            amount=100.0,
            budget_date=today,
            series=series,
        )

        # Future budget
        budget_w2 = Budget.objects.create(
            user=self.owner,
            workspace=self.workspace,
            category=self.category_groceries,
            currency=self.currency_usd,
            title="Groceries",
            amount=100.0,
            budget_date=today + datetime.timedelta(days=7),
            series=series,
        )

        # Change amount
        validated_data = {"amount": 150.0}
        new_series = BudgetSeriesService.update_budget_series(budget_w1, validated_data)

        # Should create new series
        self.assertIsNotNone(new_series)
        self.assertNotEqual(new_series.uuid, series.uuid)
        self.assertEqual(new_series.amount, 150.0)

        # Old series should be stopped
        series.refresh_from_db()
        self.assertIsNotNone(series.until)

        # Future budget should be reassigned to new series
        budget_w2.refresh_from_db()
        self.assertEqual(budget_w2.series.uuid, new_series.uuid)
        # Amount should be updated (no transactions)
        self.assertEqual(budget_w2.amount, 150.0)

    def test_category_change_splits_series(self):
        """Test changing category creates a new series"""
        today = datetime.date(2024, 1, 1)

        series = BudgetSeries.objects.create(
            user=self.owner,
            workspace=self.workspace,
            title="Groceries",
            category=self.category_groceries,
            currency=self.currency_usd,
            amount=100.0,
            start_date=today,
            frequency=BudgetSeries.Frequency.WEEKLY,
            interval=1,
        )

        budget = Budget.objects.create(
            user=self.owner,
            workspace=self.workspace,
            category=self.category_groceries,
            currency=self.currency_usd,
            title="Groceries",
            amount=100.0,
            budget_date=today,
            series=series,
        )

        # Change category
        validated_data = {"category": self.category_transport}
        new_series = BudgetSeriesService.update_budget_series(budget, validated_data)

        # Should create new series
        self.assertIsNotNone(new_series)
        self.assertNotEqual(new_series.uuid, series.uuid)
        self.assertEqual(new_series.category.uuid, self.category_transport.uuid)

    def test_future_budget_with_transaction_not_updated(self):
        """Test that future budgets with transactions are reassigned but values not updated"""
        today = datetime.date(2024, 1, 1)

        series = BudgetSeries.objects.create(
            user=self.owner,
            workspace=self.workspace,
            title="Groceries",
            category=self.category_groceries,
            currency=self.currency_usd,
            amount=100.0,
            start_date=today,
            frequency=BudgetSeries.Frequency.WEEKLY,
            interval=1,
        )

        budget_w1 = Budget.objects.create(
            user=self.owner,
            workspace=self.workspace,
            category=self.category_groceries,
            currency=self.currency_usd,
            title="Groceries",
            amount=100.0,
            budget_date=today,
            series=series,
        )

        # Future budget WITH transaction
        budget_w2 = Budget.objects.create(
            user=self.owner,
            workspace=self.workspace,
            category=self.category_groceries,
            currency=self.currency_usd,
            title="Groceries",
            amount=100.0,
            budget_date=today + datetime.timedelta(days=7),
            series=series,
        )

        Transaction.objects.create(
            user=self.owner,
            workspace=self.workspace,
            category=self.category_groceries,
            currency=self.currency_usd,
            account=self.account,
            budget=budget_w2,
            amount=50.0,
            transaction_date=today + datetime.timedelta(days=7),
        )

        # Change amount
        validated_data = {"amount": 150.0}
        new_series = BudgetSeriesService.update_budget_series(budget_w1, validated_data)

        # Future budget should be reassigned
        budget_w2.refresh_from_db()
        self.assertEqual(budget_w2.series.uuid, new_series.uuid)

        # But amount should NOT be updated (has transactions)
        self.assertEqual(budget_w2.amount, 100.0)

    def test_create_series_from_non_recurrent_budget(self):
        """Test adding recurrence to a non-recurrent budget creates a series"""
        today = datetime.date(2024, 1, 1)

        # Non-recurrent budget (no series)
        budget = Budget.objects.create(
            user=self.owner,
            workspace=self.workspace,
            category=self.category_groceries,
            currency=self.currency_usd,
            title="Groceries",
            amount=100.0,
            budget_date=today,
            series=None,
        )

        # Add weekly recurrence
        validated_data = {"recurrent": BudgetDuplicateType.WEEKLY.value}
        new_series = BudgetSeriesService.update_budget_series(budget, validated_data)

        # Should create new series
        self.assertIsNotNone(new_series)
        self.assertEqual(new_series.frequency, BudgetSeries.Frequency.WEEKLY)
        self.assertEqual(new_series.start_date, today)

    def test_no_series_operations_without_budget_date(self):
        """Test that budgets without budget_date don't trigger series operations"""
        # Pending budget (no date)
        budget = Budget.objects.create(
            user=self.owner,
            workspace=self.workspace,
            category=self.category_groceries,
            currency=self.currency_usd,
            title="Groceries",
            amount=100.0,
            budget_date=None,
            series=None,
        )

        # Try to add recurrence
        validated_data = {"recurrent": BudgetDuplicateType.WEEKLY.value}
        result = BudgetSeriesService.update_budget_series(budget, validated_data)

        # Should return None (no operations)
        self.assertIsNone(result)


class TestBudgetSeriesServiceStop(TestCase):
    """Test BudgetSeriesService.stop_series() method"""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            username="stopservicetest",
            email="stopservicetest@test.com",
            password="testpassword",
        )
        cls.workspace = Workspace.objects.create(
            name="Stop Service Test Workspace", owner=cls.owner
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
        Budget.objects.all().delete()
        BudgetSeries.objects.all().delete()
        Transaction.objects.all().delete()
        BudgetSeriesException.objects.all().delete()

    def test_stop_series_deletes_future_budgets_without_transactions(self):
        """Test that future budgets without transactions are deleted"""
        today = datetime.date(2024, 1, 1)

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

        # Budget within series
        Budget.objects.create(
            user=self.owner,
            workspace=self.workspace,
            category=self.category,
            currency=self.currency,
            title="Weekly Groceries",
            amount=100.0,
            budget_date=today,
            series=series,
        )

        # Future budget without transaction
        future_budget = Budget.objects.create(
            user=self.owner,
            workspace=self.workspace,
            category=self.category,
            currency=self.currency,
            title="Weekly Groceries",
            amount=100.0,
            budget_date=today + datetime.timedelta(days=7),
            series=series,
        )

        self.assertEqual(Budget.objects.count(), 2)

        # Stop series at today
        deleted, unlinked, exceptions = BudgetSeriesService.stop_series(series, today)

        # Future budget should be deleted
        self.assertEqual(deleted, 1)
        self.assertEqual(unlinked, 0)
        self.assertFalse(Budget.objects.filter(uuid=future_budget.uuid).exists())

        # Series should be stopped
        series.refresh_from_db()
        self.assertEqual(series.until, today)

    def test_stop_series_unlinks_future_budgets_with_transactions(self):
        """Test that future budgets with transactions are unlinked but preserved"""
        today = datetime.date(2024, 1, 1)

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

        Budget.objects.create(
            user=self.owner,
            workspace=self.workspace,
            category=self.category,
            currency=self.currency,
            title="Weekly Groceries",
            amount=100.0,
            budget_date=today,
            series=series,
        )

        # Future budget WITH transaction
        future_budget = Budget.objects.create(
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
            budget=future_budget,
            amount=50.0,
            transaction_date=today + datetime.timedelta(days=7),
        )

        # Stop series at today
        deleted, unlinked, exceptions = BudgetSeriesService.stop_series(series, today)

        # Future budget should be unlinked but exist
        self.assertEqual(deleted, 0)
        self.assertEqual(unlinked, 1)
        future_budget.refresh_from_db()
        self.assertIsNone(future_budget.series)
        self.assertTrue(Budget.objects.filter(uuid=future_budget.uuid).exists())

    def test_stop_series_deletes_future_exceptions(self):
        """Test that exceptions after until_date are deleted"""
        today = datetime.date(2024, 1, 1)

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

        # Exception before until_date
        exception_before = BudgetSeriesException.objects.create(
            series=series, date=today + datetime.timedelta(days=7), is_skipped=True
        )

        # Exception after until_date
        exception_after = BudgetSeriesException.objects.create(
            series=series, date=today + datetime.timedelta(days=21), is_skipped=True
        )

        self.assertEqual(BudgetSeriesException.objects.count(), 2)

        # Stop series at day 14
        until_date = today + datetime.timedelta(days=14)
        deleted, unlinked, exceptions = BudgetSeriesService.stop_series(
            series, until_date
        )

        # Exception after until_date should be deleted
        self.assertEqual(exceptions, 1)
        self.assertTrue(
            BudgetSeriesException.objects.filter(pk=exception_before.pk).exists()
        )
        self.assertFalse(
            BudgetSeriesException.objects.filter(pk=exception_after.pk).exists()
        )

    def test_stop_series_respects_start_date(self):
        """Test that until_date can't be before start_date"""
        today = datetime.date(2024, 1, 1)

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

        # Try to stop before start date
        before_start = today - datetime.timedelta(days=7)
        deleted, unlinked, exceptions = BudgetSeriesService.stop_series(
            series, before_start
        )

        # Should use start_date instead
        series.refresh_from_db()
        self.assertEqual(series.until, today)


class TestBudgetSeriesServiceTrackDeletion(TestCase):
    """Test BudgetSeriesService.track_deletion() method"""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            username="deletetest", email="deletetest@test.com", password="testpassword"
        )
        cls.workspace = Workspace.objects.create(
            name="Delete Test Workspace", owner=cls.owner
        )
        cls.owner.active_workspace = cls.workspace
        cls.owner.save()

        cls.currency = Currency.objects.create(
            code="USD", sign="$", is_base=True, workspace=cls.workspace
        )
        cls.category = Category.objects.create(
            uuid=uuid.uuid4(), name="Groceries", workspace=cls.workspace
        )

    def setUp(self):
        Budget.objects.all().delete()
        BudgetSeries.objects.all().delete()
        BudgetSeriesException.objects.all().delete()

    def test_track_deletion_creates_exception(self):
        """Test that deleting a budget in a series creates an exception"""
        today = datetime.date(2024, 1, 1)

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

        budget = Budget.objects.create(
            user=self.owner,
            workspace=self.workspace,
            category=self.category,
            currency=self.currency,
            title="Weekly Groceries",
            amount=100.0,
            budget_date=today,
            series=series,
        )

        self.assertEqual(BudgetSeriesException.objects.count(), 0)

        # Track deletion
        BudgetSeriesService.track_deletion(budget)

        # Exception should be created
        self.assertEqual(BudgetSeriesException.objects.count(), 1)
        exception = BudgetSeriesException.objects.get(series=series, date=today)
        self.assertTrue(exception.is_skipped)

    def test_track_deletion_without_series(self):
        """Test that deleting a budget without series doesn't create exception"""
        today = datetime.date(2024, 1, 1)

        budget = Budget.objects.create(
            user=self.owner,
            workspace=self.workspace,
            category=self.category,
            currency=self.currency,
            title="Groceries",
            amount=100.0,
            budget_date=today,
            series=None,
        )

        # Track deletion
        BudgetSeriesService.track_deletion(budget)

        # No exception should be created
        self.assertEqual(BudgetSeriesException.objects.count(), 0)

    def test_track_deletion_without_budget_date(self):
        """Test that deleting a pending budget doesn't create exception"""
        series = BudgetSeries.objects.create(
            user=self.owner,
            workspace=self.workspace,
            title="Weekly Groceries",
            category=self.category,
            currency=self.currency,
            amount=100.0,
            start_date=datetime.date(2024, 1, 1),
            frequency=BudgetSeries.Frequency.WEEKLY,
            interval=1,
        )

        budget = Budget.objects.create(
            user=self.owner,
            workspace=self.workspace,
            category=self.category,
            currency=self.currency,
            title="Weekly Groceries",
            amount=100.0,
            budget_date=None,  # Pending budget
            series=series,
        )

        # Track deletion
        BudgetSeriesService.track_deletion(budget)

        # No exception should be created
        self.assertEqual(BudgetSeriesException.objects.count(), 0)

    def test_track_deletion_idempotent(self):
        """Test that tracking deletion multiple times doesn't create duplicates"""
        today = datetime.date(2024, 1, 1)

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

        budget = Budget.objects.create(
            user=self.owner,
            workspace=self.workspace,
            category=self.category,
            currency=self.currency,
            title="Weekly Groceries",
            amount=100.0,
            budget_date=today,
            series=series,
        )

        # Track deletion twice
        BudgetSeriesService.track_deletion(budget)
        BudgetSeriesService.track_deletion(budget)

        # Should still only have one exception
        self.assertEqual(BudgetSeriesException.objects.count(), 1)
