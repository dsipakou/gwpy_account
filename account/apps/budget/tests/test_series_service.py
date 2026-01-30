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
from budget.models import (
    Budget,
    BudgetMulticurrency,
    BudgetSeries,
    BudgetSeriesException,
)
from budget.services.series_service import BudgetSeriesService
from categories.models import Category
from currencies.models import Currency
from rates.models import Rate
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

    def test_amount_change_updates_series_in_place(self):
        """Test changing amount updates the same series in place"""
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
        updated_series = BudgetSeriesService.update_budget_series(
            budget_w1, validated_data
        )

        # Should return SAME series (updated in place)
        self.assertIsNotNone(updated_series)
        self.assertEqual(updated_series.uuid, series.uuid)
        self.assertEqual(updated_series.amount, 150.0)

        # Series should NOT be stopped (until should still be None)
        series.refresh_from_db()
        self.assertIsNone(series.until)

        # Future budget should stay with same series
        budget_w2.refresh_from_db()
        self.assertEqual(budget_w2.series.uuid, series.uuid)
        # Amount should be updated (no transactions)
        self.assertEqual(budget_w2.amount, 150.0)

    def test_category_change_updates_series_in_place(self):
        """Test changing category updates the same series in place"""
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
        updated_series = BudgetSeriesService.update_budget_series(
            budget, validated_data
        )

        # Should return SAME series (updated in place)
        self.assertIsNotNone(updated_series)
        self.assertEqual(updated_series.uuid, series.uuid)
        self.assertEqual(updated_series.category.uuid, self.category_transport.uuid)

    def test_future_budget_with_transaction_not_updated(self):
        """Test that future budgets with transactions stay in same series but values not updated"""
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
        updated_series = BudgetSeriesService.update_budget_series(
            budget_w1, validated_data
        )

        # Future budget should stay with SAME series
        budget_w2.refresh_from_db()
        self.assertEqual(budget_w2.series.uuid, series.uuid)
        self.assertEqual(budget_w2.series.uuid, updated_series.uuid)

        # Amount should NOT be updated (has transactions)
        self.assertEqual(budget_w2.amount, 100.0)

    def test_amount_change_updates_multicurrency(self):
        """Test that changing amount also updates multicurrency conversions"""
        today = datetime.date(2024, 1, 1)

        # Create exchange rate for EUR
        Rate.objects.create(
            currency=self.currency_eur,
            base_currency=self.currency_usd,
            rate=0.85,  # Rate for conversion
            rate_date=today,
            workspace=self.workspace,
        )

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

        # Create initial multicurrency amounts
        initial_multi_w1 = BudgetMulticurrency.objects.create(
            budget=budget_w1, amount_map={"USD": 100.0, "EUR": 85.0}
        )
        initial_multi_w2 = BudgetMulticurrency.objects.create(
            budget=budget_w2, amount_map={"USD": 100.0, "EUR": 85.0}
        )

        # Store initial EUR values for comparison
        initial_eur_w1 = initial_multi_w1.amount_map["EUR"]
        initial_eur_w2 = initial_multi_w2.amount_map["EUR"]

        # Change amount to 150
        validated_data = {"amount": 150.0}
        BudgetSeriesService.update_budget_series(budget_w1, validated_data)

        # Budget amounts should be updated
        budget_w1.refresh_from_db()
        budget_w2.refresh_from_db()
        self.assertEqual(budget_w1.amount, 150.0)
        self.assertEqual(budget_w2.amount, 150.0)

        # Multicurrency amounts should be recalculated
        multi_w1 = BudgetMulticurrency.objects.get(budget=budget_w1)
        multi_w2 = BudgetMulticurrency.objects.get(budget=budget_w2)

        # USD amount should be 150
        self.assertEqual(multi_w1.amount_map["USD"], 150.0)
        self.assertEqual(multi_w2.amount_map["USD"], 150.0)

        # EUR amounts should be DIFFERENT from initial values (recalculated)
        # We're not testing the specific conversion value, just that it was updated
        self.assertNotEqual(multi_w1.amount_map["EUR"], initial_eur_w1)
        self.assertNotEqual(multi_w2.amount_map["EUR"], initial_eur_w2)

        # Both budgets should have the same EUR value (same amount, same rate)
        self.assertEqual(multi_w1.amount_map["EUR"], multi_w2.amount_map["EUR"])

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


class TestBudgetSeriesFiniteRepetitions(TestCase):
    """Test finite repetitions (count) feature for budget series"""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            username="finitetest",
            email="finitetest@test.com",
            password="testpassword",
        )
        cls.workspace = Workspace.objects.create(
            name="Finite Test Workspace", owner=cls.owner
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
        BudgetSeriesException.objects.all().delete()

    def test_create_series_with_finite_count(self):
        """Series created with count=10"""
        today = datetime.date(2024, 1, 1)

        series = BudgetSeries.objects.create(
            user=self.owner,
            workspace=self.workspace,
            title="Limited Groceries",
            category=self.category,
            currency=self.currency,
            amount=100.0,
            start_date=today,
            frequency=BudgetSeries.Frequency.WEEKLY,
            interval=1,
            count=10,
        )

        self.assertEqual(series.count, 10)

        # Materialize budgets
        date_to = datetime.datetime.combine(
            today + datetime.timedelta(days=365), datetime.time.max
        )
        BudgetSeriesService.materialize_budgets(
            workspace=self.workspace,
            date_to=date_to,
        )

        # Should create exactly 10 budgets
        budgets = Budget.objects.filter(series=series).order_by("budget_date")
        self.assertEqual(budgets.count(), 10)

        # Verify dates are exactly 7 days apart
        for i in range(9):
            self.assertEqual(
                (budgets[i + 1].budget_date - budgets[i].budget_date).days, 7
            )

    def test_update_series_increase_count(self):
        """Increasing count (10→15) updates same series"""
        today = datetime.date(2024, 1, 1)

        # Create series with count=10
        series = BudgetSeries.objects.create(
            user=self.owner,
            workspace=self.workspace,
            title="Limited Groceries",
            category=self.category,
            currency=self.currency,
            amount=100.0,
            start_date=today,
            frequency=BudgetSeries.Frequency.WEEKLY,
            interval=1,
            count=10,
        )

        budget = Budget.objects.create(
            user=self.owner,
            workspace=self.workspace,
            category=self.category,
            currency=self.currency,
            title="Limited Groceries",
            amount=100.0,
            budget_date=today,
            series=series,
        )

        # Update to count=15
        validated_data = {"number_of_repetitions": 15}
        updated_series = BudgetSeriesService.update_budget_series(
            budget, validated_data
        )

        # Should update same series, not create new one
        self.assertEqual(updated_series.uuid, series.uuid)
        series.refresh_from_db()
        self.assertEqual(series.count, 15)

        # Materialize should now create 15 budgets
        date_to = datetime.datetime.combine(
            today + datetime.timedelta(days=365), datetime.time.max
        )
        BudgetSeriesService.materialize_budgets(
            workspace=self.workspace,
            date_to=date_to,
        )
        self.assertEqual(Budget.objects.filter(series=series).count(), 15)

    def test_update_series_reduce_count_deletes_extras(self):
        """Reducing count (15→10) deletes budgets 11-15"""
        today = datetime.date(2024, 1, 1)

        # Create series with count=15
        series = BudgetSeries.objects.create(
            user=self.owner,
            workspace=self.workspace,
            title="Limited Groceries",
            category=self.category,
            currency=self.currency,
            amount=100.0,
            start_date=today,
            frequency=BudgetSeries.Frequency.WEEKLY,
            interval=1,
            count=15,
        )

        # Materialize all 15 budgets
        date_to = datetime.datetime.combine(
            today + datetime.timedelta(days=365), datetime.time.max
        )
        BudgetSeriesService.materialize_budgets(
            workspace=self.workspace,
            date_to=date_to,
        )
        self.assertEqual(Budget.objects.filter(series=series).count(), 15)

        # Get the first budget to update
        first_budget = (
            Budget.objects.filter(series=series).order_by("budget_date").first()
        )

        # Update to count=10
        validated_data = {"number_of_repetitions": 10}
        BudgetSeriesService.update_budget_series(first_budget, validated_data)

        # Should only have 10 budgets left (5 deleted)
        series.refresh_from_db()
        self.assertEqual(series.count, 10)
        self.assertEqual(Budget.objects.filter(series=series).count(), 10)

    def test_update_series_reduce_count_preserves_transactions(self):
        """Reducing count unlinks budgets with transactions"""
        today = datetime.date(2024, 1, 1)

        # Create series with count=15
        series = BudgetSeries.objects.create(
            user=self.owner,
            workspace=self.workspace,
            title="Limited Groceries",
            category=self.category,
            currency=self.currency,
            amount=100.0,
            start_date=today,
            frequency=BudgetSeries.Frequency.WEEKLY,
            interval=1,
            count=15,
        )

        # Materialize all 15 budgets
        date_to = datetime.datetime.combine(
            today + datetime.timedelta(days=365), datetime.time.max
        )
        BudgetSeriesService.materialize_budgets(
            workspace=self.workspace,
            date_to=date_to,
        )

        # Add transactions to budgets 12-15
        budgets = Budget.objects.filter(series=series).order_by("budget_date")
        for budget in budgets[11:15]:  # budgets 12-15 (0-indexed)
            Transaction.objects.create(
                user=self.owner,
                workspace=self.workspace,
                account=self.account,
                category=self.category,
                currency=self.currency,
                amount=50.0,
                transaction_date=budget.budget_date,
                budget=budget,
            )

        # Update to count=10
        first_budget = budgets[0]
        validated_data = {"number_of_repetitions": 10}
        BudgetSeriesService.update_budget_series(first_budget, validated_data)

        # Should have 10 budgets in series
        self.assertEqual(Budget.objects.filter(series=series).count(), 10)

        # Budgets 12-15 should still exist but unlinked (series=None)
        unlinked_budgets = Budget.objects.filter(
            series=None, title="Limited Groceries", user=self.owner
        )
        self.assertEqual(unlinked_budgets.count(), 4)

        # All unlinked budgets should have transactions
        for unlinked in unlinked_budgets:
            self.assertTrue(unlinked.transaction_set.exists())

    def test_count_and_until_both_respected(self):
        """Both constraints work together - whichever comes first"""
        today = datetime.date(2024, 1, 1)
        until_date = today + datetime.timedelta(days=21)  # 3 weeks

        # Create series with count=100 but until in 3 weeks
        # This tests that calculate_occurrences respects both constraints
        series = BudgetSeries.objects.create(
            user=self.owner,
            workspace=self.workspace,
            title="Limited Groceries",
            category=self.category,
            currency=self.currency,
            amount=100.0,
            start_date=today,
            frequency=BudgetSeries.Frequency.WEEKLY,
            interval=1,
            count=100,  # Large count
            until=until_date,  # But limited by date
        )

        # Test calculate_occurrences directly (this is what materialization uses)
        far_future = datetime.date(2025, 1, 1)
        occurrences = BudgetSeriesService.calculate_occurrences(series, far_future)

        # Should stop at until_date (4 weeks: days 0, 7, 14, 21)
        self.assertEqual(len(occurrences), 4)
        self.assertLessEqual(occurrences[-1], until_date)

    def test_deleted_budget_counts_toward_total(self):
        """Deleted budgets count as one of the total occurrences"""
        today = datetime.date(2024, 1, 1)

        # Create series with count=10 (10 total occurrences)
        series = BudgetSeries.objects.create(
            user=self.owner,
            workspace=self.workspace,
            title="Limited Groceries",
            category=self.category,
            currency=self.currency,
            amount=100.0,
            start_date=today,
            frequency=BudgetSeries.Frequency.WEEKLY,
            interval=1,
            count=10,
        )

        # Materialize first 5 budgets
        date_to = datetime.datetime.combine(
            today + datetime.timedelta(days=28), datetime.time.max
        )
        BudgetSeriesService.materialize_budgets(
            workspace=self.workspace,
            date_to=date_to,
        )

        # Delete budget #2 (week 2) - this counts as 1 of the 10 occurrences
        budgets = Budget.objects.filter(series=series).order_by("budget_date")
        budget_to_delete = budgets[1]
        BudgetSeriesService.track_deletion(budget_to_delete)
        budget_to_delete.delete()

        # Materialize more budgets
        date_to = datetime.datetime.combine(
            today + datetime.timedelta(days=365), datetime.time.max
        )
        BudgetSeriesService.materialize_budgets(
            workspace=self.workspace,
            date_to=date_to,
        )

        # Should have 9 budgets + 1 exception = 10 total occurrences
        self.assertEqual(Budget.objects.filter(series=series).count(), 9)
        self.assertEqual(
            BudgetSeriesException.objects.filter(
                series=series, is_skipped=True
            ).count(),
            1,
        )

        # Total occurrences should be exactly 10 (count limit)
        expected_dates = 10
        all_dates = list(
            Budget.objects.filter(series=series).values_list("budget_date", flat=True)
        )
        exception_dates = list(
            BudgetSeriesException.objects.filter(series=series).values_list(
                "date", flat=True
            )
        )
        total_dates = len(all_dates) + len(exception_dates)
        self.assertEqual(total_dates, expected_dates)

    def test_infinite_series_keeps_generating(self):
        """Series with count=None continues indefinitely"""
        today = datetime.date(2024, 1, 1)

        # Create infinite series
        series = BudgetSeries.objects.create(
            user=self.owner,
            workspace=self.workspace,
            title="Infinite Groceries",
            category=self.category,
            currency=self.currency,
            amount=100.0,
            start_date=today,
            frequency=BudgetSeries.Frequency.WEEKLY,
            interval=1,
            count=None,  # Infinite
        )

        # Materialize for 1 year
        date_to = datetime.datetime.combine(
            today + datetime.timedelta(days=365), datetime.time.max
        )
        BudgetSeriesService.materialize_budgets(
            workspace=self.workspace,
            date_to=date_to,
        )

        # Should create ~52 budgets (one per week for a year)
        budgets_year1 = Budget.objects.filter(series=series).count()
        self.assertGreater(budgets_year1, 50)
        self.assertLess(budgets_year1, 54)

        # Materialize for another year
        date_to = datetime.datetime.combine(
            today + datetime.timedelta(days=730), datetime.time.max
        )
        BudgetSeriesService.materialize_budgets(
            workspace=self.workspace,
            date_to=date_to,
        )

        # Should have ~104 budgets now (two years)
        budgets_year2 = Budget.objects.filter(series=series).count()
        self.assertGreater(budgets_year2, 100)
        self.assertLess(budgets_year2, 108)
