"""
Tests for recurrent budget conversion and frequency change functionality.

Tests cover:
- Converting recurrent budget to non-recurrent
- Changing frequency (weekly↔monthly)
- Handling future budgets with/without transactions
"""

import datetime

from django.test import TestCase
from django.contrib.auth import get_user_model

from budget.models import Budget, BudgetSeries
from budget.constants import BudgetDuplicateType
from categories.models import Category
from currencies.models import Currency
from transactions.models import Transaction
from accounts.models import Account
from workspaces.models import Workspace

User = get_user_model()


class RecurrentConversionTestCase(TestCase):
    """Test converting recurrent budgets to non-recurrent"""

    def setUp(self):
        """Set up test fixtures"""
        # Create test user first (without workspace)
        self.user = User.objects.create_user(
            email="test@example.com",
            password="testpass123",
            username="testuser",
        )

        # Create workspace with owner
        self.workspace = Workspace.objects.create(
            name="Test Workspace",
            owner=self.user,
        )

        # Set active workspace
        self.user.active_workspace = self.workspace
        self.user.save()

        # Create currency
        self.currency = Currency.objects.create(
            workspace=self.workspace,
            code="USD",
            sign="$",
            is_base=True,
        )

        # Create category
        self.category = Category.objects.create(
            workspace=self.workspace,
            name="Food",
            type="EXP",
            parent=None,
            position=0,
        )

        # Create account for transactions
        self.account = Account.objects.create(
            workspace=self.workspace,
            user=self.user,
            title="Test Account",
            description="Test account",
            is_main=True,
            category=self.category,
        )

    def test_convert_recurrent_to_non_recurrent_with_none(self):
        """Test converting a recurrent budget to non-recurrent using None"""
        # Create a monthly recurring budget
        series = BudgetSeries.objects.create(
            user=self.user,
            workspace=self.workspace,
            title="Monthly Groceries",
            category=self.category,
            currency=self.currency,
            amount=500.00,
            start_date=datetime.date(2024, 1, 1),
            frequency=BudgetSeries.Frequency.MONTHLY,
            interval=1,
        )

        # Create the main budget
        budget = Budget.objects.create(
            user=self.user,
            workspace=self.workspace,
            title="Monthly Groceries",
            category=self.category,
            currency=self.currency,
            amount=500.00,
            budget_date=datetime.date(2024, 1, 1),
            series=series,
        )

        # Create future budgets (simulating materialization)
        future_budget_1 = Budget.objects.create(
            user=self.user,
            workspace=self.workspace,
            title="Monthly Groceries",
            category=self.category,
            currency=self.currency,
            amount=500.00,
            budget_date=datetime.date(2024, 2, 1),
            series=series,
        )

        future_budget_2 = Budget.objects.create(
            user=self.user,
            workspace=self.workspace,
            title="Monthly Groceries",
            category=self.category,
            currency=self.currency,
            amount=500.00,
            budget_date=datetime.date(2024, 3, 1),
            series=series,
        )

        # Convert to non-recurrent by setting recurrent to None
        from budget.serializers import BudgetSerializer
        from rest_framework.request import Request
        from rest_framework.test import APIRequestFactory

        factory = APIRequestFactory()
        request = factory.put("/")
        request.user = self.user

        serializer = BudgetSerializer(
            budget,
            data={"recurrent": None},
            partial=True,
            context={"request": Request(request)},
        )
        serializer.is_valid(raise_exception=True)

        # Simulate perform_update
        from budget.views import BudgetDetails

        view = BudgetDetails()
        view.kwargs = {"uuid": budget.uuid}
        view.request = request
        view.perform_update(serializer)

        # Refresh from database
        budget.refresh_from_db()
        series.refresh_from_db()

        # Verify budget is unlinked
        self.assertIsNone(budget.series)
        self.assertIsNone(budget.recurrent_type)

        # Verify series is stopped
        self.assertIsNotNone(series.until)
        self.assertEqual(series.until, datetime.date(2023, 12, 1))

        # Verify future budgets are deleted
        self.assertFalse(Budget.objects.filter(uuid=future_budget_1.uuid).exists())
        self.assertFalse(Budget.objects.filter(uuid=future_budget_2.uuid).exists())

    def test_convert_recurrent_to_non_recurrent_with_empty_string(self):
        """Test converting a recurrent budget to non-recurrent using empty string (real frontend behavior)"""
        # Create a monthly recurring budget
        series = BudgetSeries.objects.create(
            user=self.user,
            workspace=self.workspace,
            title="Monthly Rent",
            category=self.category,
            currency=self.currency,
            amount=1500.00,
            start_date=datetime.date(2024, 1, 1),
            frequency=BudgetSeries.Frequency.MONTHLY,
            interval=1,
        )

        budget = Budget.objects.create(
            user=self.user,
            workspace=self.workspace,
            title="Monthly Rent",
            category=self.category,
            currency=self.currency,
            amount=1500.00,
            budget_date=datetime.date(2024, 1, 1),
            series=series,
        )

        # Create future budgets
        future_budget_1 = Budget.objects.create(
            user=self.user,
            workspace=self.workspace,
            title="Monthly Rent",
            category=self.category,
            currency=self.currency,
            amount=1500.00,
            budget_date=datetime.date(2024, 2, 1),
            series=series,
        )

        future_budget_2 = Budget.objects.create(
            user=self.user,
            workspace=self.workspace,
            title="Monthly Rent",
            category=self.category,
            currency=self.currency,
            amount=1500.00,
            budget_date=datetime.date(2024, 3, 1),
            series=series,
        )

        # Convert to non-recurrent by setting recurrent to empty string (frontend sends "")
        from budget.serializers import BudgetSerializer
        from rest_framework.request import Request
        from rest_framework.test import APIRequestFactory

        factory = APIRequestFactory()
        request = factory.put("/")
        request.user = self.user

        serializer = BudgetSerializer(
            budget,
            data={"recurrent": ""},  # Empty string instead of None
            partial=True,
            context={"request": Request(request)},
        )
        serializer.is_valid(raise_exception=True)

        # Simulate perform_update
        from budget.views import BudgetDetails

        view = BudgetDetails()
        view.kwargs = {"uuid": budget.uuid}
        view.request = request
        view.perform_update(serializer)

        # Refresh from database
        budget.refresh_from_db()
        series.refresh_from_db()

        # Verify budget is unlinked
        self.assertIsNone(budget.series)
        self.assertIsNone(budget.recurrent_type)

        # Verify series is stopped
        self.assertIsNotNone(series.until)
        self.assertEqual(series.until, datetime.date(2023, 12, 1))

        # Verify future budgets are deleted
        self.assertFalse(Budget.objects.filter(uuid=future_budget_1.uuid).exists())
        self.assertFalse(Budget.objects.filter(uuid=future_budget_2.uuid).exists())

    def test_convert_with_transaction_protection(self):
        """Test that future budgets with transactions are preserved"""
        # Create a monthly recurring budget
        series = BudgetSeries.objects.create(
            user=self.user,
            workspace=self.workspace,
            title="Monthly Groceries",
            category=self.category,
            currency=self.currency,
            amount=500.00,
            start_date=datetime.date(2024, 1, 1),
            frequency=BudgetSeries.Frequency.MONTHLY,
            interval=1,
        )

        budget = Budget.objects.create(
            user=self.user,
            workspace=self.workspace,
            title="Monthly Groceries",
            category=self.category,
            currency=self.currency,
            amount=500.00,
            budget_date=datetime.date(2024, 1, 1),
            series=series,
        )

        # Create future budget with transaction
        future_budget = Budget.objects.create(
            user=self.user,
            workspace=self.workspace,
            title="Monthly Groceries",
            category=self.category,
            currency=self.currency,
            amount=500.00,
            budget_date=datetime.date(2024, 2, 1),
            series=series,
        )

        # Add transaction to future budget
        Transaction.objects.create(
            user=self.user,
            workspace=self.workspace,
            account=self.account,
            budget=future_budget,
            category=self.category,
            currency=self.currency,
            amount=50.00,
            transaction_date=datetime.date(2024, 2, 5),
            description="Test transaction",
        )

        # Convert to non-recurrent
        from budget.serializers import BudgetSerializer
        from rest_framework.request import Request
        from rest_framework.test import APIRequestFactory

        factory = APIRequestFactory()
        request = factory.put("/")
        request.user = self.user

        serializer = BudgetSerializer(
            budget,
            data={"recurrent": None},
            partial=True,
            context={"request": Request(request)},
        )
        serializer.is_valid(raise_exception=True)

        from budget.views import BudgetDetails

        view = BudgetDetails()
        view.kwargs = {"uuid": budget.uuid}
        view.request = request
        view.perform_update(serializer)

        # Verify future budget still exists but is unlinked
        future_budget.refresh_from_db()
        self.assertIsNone(future_budget.series)
        self.assertEqual(future_budget.transaction_set.count(), 1)

    def test_frequency_change_weekly_to_monthly(self):
        """Test changing frequency from weekly to monthly"""
        # Create a weekly recurring budget
        series = BudgetSeries.objects.create(
            user=self.user,
            workspace=self.workspace,
            title="Weekly Groceries",
            category=self.category,
            currency=self.currency,
            amount=100.00,
            start_date=datetime.date(2024, 1, 1),
            frequency=BudgetSeries.Frequency.WEEKLY,
            interval=1,
        )

        budget = Budget.objects.create(
            user=self.user,
            workspace=self.workspace,
            title="Weekly Groceries",
            category=self.category,
            currency=self.currency,
            amount=100.00,
            budget_date=datetime.date(2024, 1, 1),
            series=series,
        )

        # Create future weekly budgets
        future_budget_1 = Budget.objects.create(
            user=self.user,
            workspace=self.workspace,
            title="Weekly Groceries",
            category=self.category,
            currency=self.currency,
            amount=100.00,
            budget_date=datetime.date(2024, 1, 8),
            series=series,
        )

        future_budget_2 = Budget.objects.create(
            user=self.user,
            workspace=self.workspace,
            title="Weekly Groceries",
            category=self.category,
            currency=self.currency,
            amount=100.00,
            budget_date=datetime.date(2024, 1, 15),
            series=series,
        )

        # Change to monthly
        from budget.serializers import BudgetSerializer
        from rest_framework.request import Request
        from rest_framework.test import APIRequestFactory

        factory = APIRequestFactory()
        request = factory.put("/")
        request.user = self.user

        serializer = BudgetSerializer(
            budget,
            data={"recurrent": BudgetDuplicateType.MONTHLY.value},
            partial=True,
            context={"request": Request(request)},
        )
        serializer.is_valid(raise_exception=True)

        from budget.views import BudgetDetails

        view = BudgetDetails()
        view.kwargs = {"uuid": budget.uuid}
        view.request = request
        view.perform_update(serializer)

        # Refresh from database
        budget.refresh_from_db()
        series.refresh_from_db()

        # Verify old series is stopped
        self.assertIsNotNone(series.until)
        self.assertEqual(series.until, datetime.date(2023, 12, 25))

        # Verify new series was created with monthly frequency
        self.assertIsNotNone(budget.series)
        self.assertNotEqual(budget.series.uuid, series.uuid)
        self.assertEqual(budget.series.frequency, BudgetSeries.Frequency.MONTHLY)

        # Verify future weekly budgets are deleted
        self.assertFalse(Budget.objects.filter(uuid=future_budget_1.uuid).exists())
        self.assertFalse(Budget.objects.filter(uuid=future_budget_2.uuid).exists())

    def test_frequency_change_monthly_to_weekly(self):
        """Test changing frequency from monthly to weekly"""
        # Create a monthly recurring budget
        series = BudgetSeries.objects.create(
            user=self.user,
            workspace=self.workspace,
            title="Monthly Rent",
            category=self.category,
            currency=self.currency,
            amount=1500.00,
            start_date=datetime.date(2024, 1, 1),
            frequency=BudgetSeries.Frequency.MONTHLY,
            interval=1,
        )

        budget = Budget.objects.create(
            user=self.user,
            workspace=self.workspace,
            title="Monthly Rent",
            category=self.category,
            currency=self.currency,
            amount=1500.00,
            budget_date=datetime.date(2024, 1, 1),
            series=series,
        )

        # Create future monthly budgets
        future_budget = Budget.objects.create(
            user=self.user,
            workspace=self.workspace,
            title="Monthly Rent",
            category=self.category,
            currency=self.currency,
            amount=1500.00,
            budget_date=datetime.date(2024, 2, 1),
            series=series,
        )

        # Change to weekly
        from budget.serializers import BudgetSerializer
        from rest_framework.request import Request
        from rest_framework.test import APIRequestFactory

        factory = APIRequestFactory()
        request = factory.put("/")
        request.user = self.user

        serializer = BudgetSerializer(
            budget,
            data={"recurrent": BudgetDuplicateType.WEEKLY.value},
            partial=True,
            context={"request": Request(request)},
        )
        serializer.is_valid(raise_exception=True)

        from budget.views import BudgetDetails

        view = BudgetDetails()
        view.kwargs = {"uuid": budget.uuid}
        view.request = request
        view.perform_update(serializer)

        # Refresh from database
        budget.refresh_from_db()
        series.refresh_from_db()

        # Verify old series is stopped
        self.assertIsNotNone(series.until)
        self.assertEqual(series.until, datetime.date(2023, 12, 1))

        # Verify new series was created with weekly frequency
        self.assertIsNotNone(budget.series)
        self.assertNotEqual(budget.series.uuid, series.uuid)
        self.assertEqual(budget.series.frequency, BudgetSeries.Frequency.WEEKLY)

        # Verify future monthly budget is deleted
        self.assertFalse(Budget.objects.filter(uuid=future_budget.uuid).exists())

    def test_frequency_change_with_transaction_protection(self):
        """Test that frequency change preserves budgets with transactions"""
        # Create a monthly recurring budget
        series = BudgetSeries.objects.create(
            user=self.user,
            workspace=self.workspace,
            title="Monthly Groceries",
            category=self.category,
            currency=self.currency,
            amount=500.00,
            start_date=datetime.date(2024, 1, 1),
            frequency=BudgetSeries.Frequency.MONTHLY,
            interval=1,
        )

        budget = Budget.objects.create(
            user=self.user,
            workspace=self.workspace,
            title="Monthly Groceries",
            category=self.category,
            currency=self.currency,
            amount=500.00,
            budget_date=datetime.date(2024, 1, 1),
            series=series,
        )

        # Create future budget with transaction
        future_budget_with_tx = Budget.objects.create(
            user=self.user,
            workspace=self.workspace,
            title="Monthly Groceries",
            category=self.category,
            currency=self.currency,
            amount=500.00,
            budget_date=datetime.date(2024, 2, 1),
            series=series,
        )

        Transaction.objects.create(
            user=self.user,
            workspace=self.workspace,
            account=self.account,
            budget=future_budget_with_tx,
            category=self.category,
            currency=self.currency,
            amount=50.00,
            transaction_date=datetime.date(2024, 2, 5),
            description="Test transaction",
        )

        # Create future budget without transaction
        future_budget_empty = Budget.objects.create(
            user=self.user,
            workspace=self.workspace,
            title="Monthly Groceries",
            category=self.category,
            currency=self.currency,
            amount=500.00,
            budget_date=datetime.date(2024, 3, 1),
            series=series,
        )

        # Change to weekly
        from budget.serializers import BudgetSerializer
        from rest_framework.request import Request
        from rest_framework.test import APIRequestFactory

        factory = APIRequestFactory()
        request = factory.put("/")
        request.user = self.user

        serializer = BudgetSerializer(
            budget,
            data={"recurrent": BudgetDuplicateType.WEEKLY.value},
            partial=True,
            context={"request": Request(request)},
        )
        serializer.is_valid(raise_exception=True)

        from budget.views import BudgetDetails

        view = BudgetDetails()
        view.kwargs = {"uuid": budget.uuid}
        view.request = request
        view.perform_update(serializer)

        # Verify future budget with transaction still exists but is unlinked
        future_budget_with_tx.refresh_from_db()
        self.assertIsNone(future_budget_with_tx.series)
        self.assertEqual(future_budget_with_tx.transaction_set.count(), 1)

        # Verify empty future budget is deleted
        self.assertFalse(Budget.objects.filter(uuid=future_budget_empty.uuid).exists())
