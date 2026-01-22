import datetime
import uuid
from unittest.mock import patch

from django.test import TestCase

from accounts.models import Account
from budget.constants import BudgetDuplicateType
from budget.models import Budget, BudgetMulticurrency, BudgetSeries
from budget.serializers import BudgetSerializer
from budget.services import BudgetService
from categories.models import Category
from currencies.models import Currency
from transactions.models import Transaction, TransactionMulticurrency
from users.models import User
from workspaces.models import Workspace


class TestBudgetServiceOccasional(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            username="testuser", password="testpassword"
        )
        cls.workspace = Workspace.objects.create(name="Test Workspace", owner=cls.owner)
        cls.currency = Currency.objects.create(
            code="USD", sign="$", is_base=True, workspace=cls.workspace
        )
        cls.category = Category.objects.create(
            uuid=uuid.uuid4(), name="Transportation", workspace=cls.workspace
        )
        cls.account = Account.objects.create(
            uuid=uuid.uuid4(),
            title="Test Account",
            description="Test account for transactions",
            is_main=True,
            user=cls.owner,
            workspace=cls.workspace,
            category=cls.category,
        )

    def setUp(self):
        # Clean up any existing budgets/transactions before each test
        Budget.objects.all().delete()
        Transaction.objects.all().delete()

    def test_get_occasional_budget_candidates_with_historical_budgets(self):
        """Test that occasional budgets from last 6 months are suggested for duplication"""
        today = datetime.date.today()

        # Create occasional budgets over the last 6 months
        fuel_budget_3_months = Budget.objects.create(
            uuid=uuid.uuid4(),
            user=self.owner,
            workspace=self.workspace,
            category=self.category,
            currency=self.currency,
            title="Fuel",
            amount=80.0,
            budget_date=today - datetime.timedelta(days=90),
            recurrent=BudgetDuplicateType.OCCASIONAL,
        )

        fuel_budget_5_months = Budget.objects.create(
            uuid=uuid.uuid4(),
            user=self.owner,
            workspace=self.workspace,
            category=self.category,
            currency=self.currency,
            title="Fuel",
            amount=75.0,
            budget_date=today - datetime.timedelta(days=150),
            recurrent=BudgetDuplicateType.OCCASIONAL,
        )

        maintenance_budget = Budget.objects.create(
            uuid=uuid.uuid4(),
            user=self.owner,
            workspace=self.workspace,
            category=self.category,
            currency=self.currency,
            title="Car Maintenance",
            amount=200.0,
            budget_date=today - datetime.timedelta(days=60),
            recurrent=BudgetDuplicateType.OCCASIONAL,
        )

        # Create corresponding multicurrency entries
        BudgetMulticurrency.objects.create(
            budget=fuel_budget_3_months, amount_map={"USD": 80.0}
        )
        BudgetMulticurrency.objects.create(
            budget=fuel_budget_5_months, amount_map={"USD": 75.0}
        )
        BudgetMulticurrency.objects.create(
            budget=maintenance_budget, amount_map={"USD": 200.0}
        )

        # Create some transactions for these budgets
        fuel_transaction = Transaction.objects.create(
            uuid=uuid.uuid4(),
            user=self.owner,
            workspace=self.workspace,
            category=self.category,
            currency=self.currency,
            account=self.account,
            budget=fuel_budget_3_months,
            amount=82.0,
            transaction_date=today - datetime.timedelta(days=85),
        )

        TransactionMulticurrency.objects.create(
            transaction=fuel_transaction, amount_map={"USD": 82.0}
        )

        queryset = Budget.objects.filter(workspace=self.workspace)

        with (
            patch("budget.utils.get_first_day_of_prev_month") as mock_start,
            patch("budget.utils.get_last_day_of_prev_month") as mock_end,
        ):
            mock_start.return_value = today.replace(day=1) - datetime.timedelta(days=1)
            mock_end.return_value = today.replace(day=1) - datetime.timedelta(days=1)

            candidates = BudgetService.get_duplicate_budget_candidates(
                queryset, BudgetDuplicateType.OCCASIONAL
            )

        # Should suggest both Fuel and Car Maintenance
        self.assertEqual(len(candidates), 2)

        titles = [candidate["title"] for candidate in candidates]
        self.assertIn("Fuel", titles)
        self.assertIn("Car Maintenance", titles)

        # Check that amounts are calculated properly
        fuel_candidate = next(c for c in candidates if c["title"] == "Fuel")
        maintenance_candidate = next(
            c for c in candidates if c["title"] == "Car Maintenance"
        )

        # Fuel should have weighted average based on frequency and usage
        self.assertGreater(fuel_candidate["amount"], 0)
        self.assertEqual(
            maintenance_candidate["amount"], 200.0
        )  # No transactions, uses original amount

    def test_get_occasional_budget_candidates_excludes_existing_budgets(self):
        """Test that already existing budgets for the upcoming period are not suggested"""
        today = datetime.date.today()

        # Create historical occasional budget
        Budget.objects.create(
            uuid=uuid.uuid4(),
            user=self.owner,
            workspace=self.workspace,
            category=self.category,
            currency=self.currency,
            title="Insurance",
            amount=150.0,
            budget_date=today - datetime.timedelta(days=90),
            recurrent=BudgetDuplicateType.OCCASIONAL,
        )

        # Create budget that already exists for upcoming period
        with (
            patch("budget.utils.get_first_day_of_prev_month") as mock_start,
            patch("budget.utils.get_last_day_of_prev_month") as mock_end,
        ):
            # Get proper previous month dates
            from dateutil.relativedelta import relativedelta

            first_of_current_month = today.replace(day=1)
            first_of_prev_month = first_of_current_month - relativedelta(months=1)
            prev_month_start = first_of_prev_month
            prev_month_end = first_of_current_month - datetime.timedelta(days=1)
            mock_start.return_value = prev_month_start
            mock_end.return_value = prev_month_end

            # Calculate the upcoming date like the service does
            # This should match the logic in _get_occasional_budget_candidates:
            # upcoming_date = mapping["start_date"](pivot_date) + mapping["relative_date"]
            upcoming_date = prev_month_start + relativedelta(months=1)

            Budget.objects.create(
                uuid=uuid.uuid4(),
                user=self.owner,
                workspace=self.workspace,
                category=self.category,
                currency=self.currency,
                title="Insurance",
                amount=150.0,
                budget_date=upcoming_date,
                recurrent=BudgetDuplicateType.OCCASIONAL,
            )

        queryset = Budget.objects.filter(workspace=self.workspace)

        with (
            patch("budget.utils.get_first_day_of_prev_month") as mock_start,
            patch("budget.utils.get_last_day_of_prev_month") as mock_end,
        ):
            mock_start.return_value = prev_month_start
            mock_end.return_value = prev_month_end

            candidates = BudgetService.get_duplicate_budget_candidates(
                queryset, BudgetDuplicateType.OCCASIONAL
            )

        # Should not suggest Insurance since it already exists for upcoming period
        self.assertEqual(len(candidates), 0)

    def test_get_occasional_budget_candidates_empty_when_no_historical_data(self):
        """Test that no candidates are returned when there are no occasional budgets in history"""
        queryset = Budget.objects.filter(workspace=self.workspace)

        with (
            patch("budget.utils.get_first_day_of_prev_month") as mock_start,
            patch("budget.utils.get_last_day_of_prev_month") as mock_end,
        ):
            mock_start.return_value = datetime.date.today().replace(
                day=1
            ) - datetime.timedelta(days=1)
            mock_end.return_value = datetime.date.today().replace(
                day=1
            ) - datetime.timedelta(days=1)

            candidates = BudgetService.get_duplicate_budget_candidates(
                queryset, BudgetDuplicateType.OCCASIONAL
            )

        self.assertEqual(len(candidates), 0)

    def test_get_occasional_budget_candidates_frequency_weighting(self):
        """Test that amount suggestions are weighted by frequency"""
        today = datetime.date.today()

        # Create multiple fuel budgets to test frequency weighting
        for i in range(3):  # 3 out of 6 months = 50% frequency
            budget = Budget.objects.create(
                uuid=uuid.uuid4(),
                user=self.owner,
                workspace=self.workspace,
                category=self.category,
                currency=self.currency,
                title="Fuel",
                amount=100.0,
                budget_date=today - datetime.timedelta(days=30 * (i + 1)),
                recurrent=BudgetDuplicateType.OCCASIONAL,
            )

            # Create transaction with same amount
            transaction = Transaction.objects.create(
                uuid=uuid.uuid4(),
                user=self.owner,
                workspace=self.workspace,
                category=self.category,
                currency=self.currency,
                account=self.account,
                budget=budget,
                amount=100.0,
                transaction_date=today - datetime.timedelta(days=30 * (i + 1)),
            )

            TransactionMulticurrency.objects.create(
                transaction=transaction, amount_map={"USD": 100.0}
            )

        queryset = Budget.objects.filter(workspace=self.workspace)

        with (
            patch("budget.utils.get_first_day_of_prev_month") as mock_start,
            patch("budget.utils.get_last_day_of_prev_month") as mock_end,
        ):
            mock_start.return_value = today.replace(day=1) - datetime.timedelta(days=1)
            mock_end.return_value = today.replace(day=1) - datetime.timedelta(days=1)

            candidates = BudgetService.get_duplicate_budget_candidates(
                queryset, BudgetDuplicateType.OCCASIONAL
            )

        self.assertEqual(len(candidates), 1)
        fuel_candidate = candidates[0]

        # With 50% frequency (3/6 months), suggested amount should be 50.0 (100 * 0.5)
        self.assertEqual(fuel_candidate["amount"], 50.0)
        self.assertEqual(fuel_candidate["title"], "Fuel")

    def test_get_duplicate_budget_candidates_routes_to_occasional_method(self):
        """Test that get_duplicate_budget_candidates routes OCCASIONAL type to the correct method"""
        today = datetime.date.today()

        # Create an occasional budget
        Budget.objects.create(
            uuid=uuid.uuid4(),
            user=self.owner,
            workspace=self.workspace,
            category=self.category,
            currency=self.currency,
            title="Test Occasional",
            amount=50.0,
            budget_date=today - datetime.timedelta(days=90),
            recurrent=BudgetDuplicateType.OCCASIONAL,
        )

        queryset = Budget.objects.filter(workspace=self.workspace)

        with patch.object(
            BudgetService, "_get_occasional_budget_candidates"
        ) as mock_occasional:
            mock_occasional.return_value = []

            BudgetService.get_duplicate_budget_candidates(
                queryset, BudgetDuplicateType.OCCASIONAL
            )

            mock_occasional.assert_called_once_with(queryset, None)

    def test_monthly_and_weekly_budgets_still_work(self):
        """Test that existing MONTHLY and WEEKLY logic is not affected"""
        today = datetime.date.today()

        # Create monthly budget in previous month
        Budget.objects.create(
            uuid=uuid.uuid4(),
            user=self.owner,
            workspace=self.workspace,
            category=self.category,
            currency=self.currency,
            title="Monthly Expense",
            amount=200.0,
            budget_date=today - datetime.timedelta(days=30),
            recurrent=BudgetDuplicateType.MONTHLY,
        )

        queryset = Budget.objects.filter(workspace=self.workspace)

        with (
            patch("budget.utils.get_first_day_of_prev_month") as mock_start,
            patch("budget.utils.get_last_day_of_prev_month") as mock_end,
        ):
            mock_start.return_value = today - datetime.timedelta(days=30)
            mock_end.return_value = today - datetime.timedelta(days=1)

            candidates = BudgetService.get_duplicate_budget_candidates(
                queryset, BudgetDuplicateType.MONTHLY
            )

        # Should find the monthly budget (this tests that existing logic still works)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["title"], "Monthly Expense")


class TestBudgetSeriesCreation(TestCase):
    """Test BudgetSeries creation and linking via BudgetSerializer"""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            username="seriesuser", password="testpassword"
        )
        cls.workspace = Workspace.objects.create(
            name="Series Test Workspace", owner=cls.owner
        )
        cls.owner.active_workspace = cls.workspace
        cls.owner.save()

        cls.currency = Currency.objects.create(
            code="USD", sign="$", is_base=True, workspace=cls.workspace
        )
        cls.category = Category.objects.create(
            uuid=uuid.uuid4(), name="Transportation", workspace=cls.workspace
        )

    def setUp(self):
        # Clean up before each test
        Budget.objects.all().delete()
        BudgetSeries.objects.all().delete()

    def test_weekly_budget_creates_budget_series(self):
        """Test that creating a WEEKLY budget automatically creates a BudgetSeries"""
        today = datetime.date.today()

        data = {
            "user": self.owner.uuid,
            "category": self.category.uuid,
            "currency": self.currency.uuid,
            "title": "Weekly Fuel",
            "amount": 100.0,
            "recurrent": BudgetDuplicateType.WEEKLY.value,
            "budget_date": today,
        }

        serializer = BudgetSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)

        budget = serializer.save()

        # Verify BudgetSeries was created
        self.assertIsNotNone(budget.series)
        self.assertEqual(budget.series.title, "Weekly Fuel")
        self.assertEqual(budget.series.frequency, BudgetSeries.Frequency.WEEKLY)
        self.assertEqual(budget.series.user, self.owner)
        self.assertEqual(budget.series.workspace, self.workspace)
        self.assertEqual(budget.series.amount, 100.0)
        self.assertEqual(budget.series.start_date, today)
        self.assertEqual(budget.series.interval, 1)
        self.assertIsNone(budget.series.count)
        self.assertIsNone(budget.series.until)

        # Verify only one BudgetSeries was created
        self.assertEqual(BudgetSeries.objects.count(), 1)

    def test_monthly_budget_creates_budget_series(self):
        """Test that creating a MONTHLY budget automatically creates a BudgetSeries"""
        today = datetime.date.today()

        data = {
            "user": self.owner.uuid,
            "category": self.category.uuid,
            "currency": self.currency.uuid,
            "title": "Monthly Rent",
            "amount": 1500.0,
            "recurrent": BudgetDuplicateType.MONTHLY.value,
            "budget_date": today,
        }

        serializer = BudgetSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)

        budget = serializer.save()

        # Verify BudgetSeries was created
        self.assertIsNotNone(budget.series)
        self.assertEqual(budget.series.title, "Monthly Rent")
        self.assertEqual(budget.series.frequency, BudgetSeries.Frequency.MONTHLY)
        self.assertEqual(budget.series.amount, 1500.0)

        # Verify only one BudgetSeries was created
        self.assertEqual(BudgetSeries.objects.count(), 1)

    def test_occasional_budget_does_not_create_series(self):
        """Test that OCCASIONAL budgets do not create a BudgetSeries"""
        today = datetime.date.today()

        data = {
            "user": self.owner.uuid,
            "category": self.category.uuid,
            "currency": self.currency.uuid,
            "title": "Car Repair",
            "amount": 500.0,
            "recurrent": BudgetDuplicateType.OCCASIONAL.value,
            "budget_date": today,
        }

        serializer = BudgetSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)

        budget = serializer.save()

        # Verify no BudgetSeries was created
        self.assertIsNone(budget.series)
        self.assertEqual(BudgetSeries.objects.count(), 0)

    def test_same_title_and_frequency_reuses_budget_series(self):
        """Test that budgets with same title+user+frequency share the same BudgetSeries"""
        today = datetime.date.today()

        # Create first budget
        data1 = {
            "user": self.owner.uuid,
            "category": self.category.uuid,
            "currency": self.currency.uuid,
            "title": "Weekly Groceries",
            "amount": 150.0,
            "recurrent": BudgetDuplicateType.WEEKLY.value,
            "budget_date": today,
        }

        serializer1 = BudgetSerializer(data=data1)
        self.assertTrue(serializer1.is_valid(), serializer1.errors)
        budget1 = serializer1.save()

        # Create second budget with same title and frequency
        data2 = {
            "user": self.owner.uuid,
            "category": self.category.uuid,
            "currency": self.currency.uuid,
            "title": "Weekly Groceries",
            "amount": 150.0,
            "recurrent": BudgetDuplicateType.WEEKLY.value,
            "budget_date": today + datetime.timedelta(days=7),
        }

        serializer2 = BudgetSerializer(data=data2)
        self.assertTrue(serializer2.is_valid(), serializer2.errors)
        budget2 = serializer2.save()

        # Verify both budgets share the same series
        self.assertIsNotNone(budget1.series)
        self.assertIsNotNone(budget2.series)
        self.assertEqual(budget1.series.uuid, budget2.series.uuid)

        # Verify only one BudgetSeries was created
        self.assertEqual(BudgetSeries.objects.count(), 1)

        # Verify the series has correct data
        series = BudgetSeries.objects.first()
        self.assertEqual(series.title, "Weekly Groceries")
        self.assertEqual(series.frequency, BudgetSeries.Frequency.WEEKLY)

    def test_different_frequency_creates_separate_series(self):
        """Test that same title but different frequency creates separate BudgetSeries"""
        today = datetime.date.today()

        # Create WEEKLY budget
        data1 = {
            "user": self.owner.uuid,
            "category": self.category.uuid,
            "currency": self.currency.uuid,
            "title": "Fuel",
            "amount": 100.0,
            "recurrent": BudgetDuplicateType.WEEKLY.value,
            "budget_date": today,
        }

        serializer1 = BudgetSerializer(data=data1)
        self.assertTrue(serializer1.is_valid(), serializer1.errors)
        budget1 = serializer1.save()

        # Create MONTHLY budget with same title
        data2 = {
            "user": self.owner.uuid,
            "category": self.category.uuid,
            "currency": self.currency.uuid,
            "title": "Fuel",
            "amount": 400.0,
            "recurrent": BudgetDuplicateType.MONTHLY.value,
            "budget_date": today,
        }

        serializer2 = BudgetSerializer(data=data2)
        self.assertTrue(serializer2.is_valid(), serializer2.errors)
        budget2 = serializer2.save()

        # Verify both budgets have series but different ones
        self.assertIsNotNone(budget1.series)
        self.assertIsNotNone(budget2.series)
        self.assertNotEqual(budget1.series.uuid, budget2.series.uuid)

        # Verify two BudgetSeries were created
        self.assertEqual(BudgetSeries.objects.count(), 2)

        # Verify each series has correct frequency
        self.assertEqual(budget1.series.frequency, BudgetSeries.Frequency.WEEKLY)
        self.assertEqual(budget2.series.frequency, BudgetSeries.Frequency.MONTHLY)

    def test_budget_without_recurrent_field_does_not_create_series(self):
        """Test that budgets without recurrent field don't create BudgetSeries"""
        today = datetime.date.today()

        data = {
            "user": self.owner.uuid,
            "category": self.category.uuid,
            "currency": self.currency.uuid,
            "title": "One-time Expense",
            "amount": 250.0,
            "budget_date": today,
            # No recurrent field
        }

        serializer = BudgetSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)

        budget = serializer.save()

        # Verify no BudgetSeries was created
        self.assertIsNone(budget.series)
        self.assertEqual(BudgetSeries.objects.count(), 0)

    def test_series_links_correct_category_and_currency(self):
        """Test that BudgetSeries is created with correct category and currency"""
        today = datetime.date.today()

        # Create another category for testing
        food_category = Category.objects.create(
            uuid=uuid.uuid4(), name="Food", workspace=self.workspace
        )

        data = {
            "user": self.owner.uuid,
            "category": food_category.uuid,
            "currency": self.currency.uuid,
            "title": "Weekly Dining",
            "amount": 200.0,
            "recurrent": BudgetDuplicateType.WEEKLY.value,
            "budget_date": today,
        }

        serializer = BudgetSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)

        budget = serializer.save()

        # Verify series has correct category and currency
        self.assertEqual(budget.series.category.uuid, food_category.uuid)
        self.assertEqual(budget.series.currency.uuid, self.currency.uuid)

    def test_multiple_users_with_same_title_create_separate_series(self):
        """Test that different users with same budget title get separate BudgetSeries"""
        # Create second user
        second_user = User.objects.create_user(
            username="seconduser", password="testpassword"
        )
        second_user.active_workspace = self.workspace
        second_user.save()

        today = datetime.date.today()

        # Create budget for first user
        data1 = {
            "user": self.owner.uuid,
            "category": self.category.uuid,
            "currency": self.currency.uuid,
            "title": "Commute",
            "amount": 50.0,
            "recurrent": BudgetDuplicateType.WEEKLY.value,
            "budget_date": today,
        }

        serializer1 = BudgetSerializer(data=data1)
        self.assertTrue(serializer1.is_valid(), serializer1.errors)
        budget1 = serializer1.save()

        # Create budget for second user with same title
        data2 = {
            "user": second_user.uuid,
            "category": self.category.uuid,
            "currency": self.currency.uuid,
            "title": "Commute",
            "amount": 75.0,
            "recurrent": BudgetDuplicateType.WEEKLY.value,
            "budget_date": today,
        }

        serializer2 = BudgetSerializer(data=data2)
        self.assertTrue(serializer2.is_valid(), serializer2.errors)
        budget2 = serializer2.save()

        # Verify both have series but different ones
        self.assertIsNotNone(budget1.series)
        self.assertIsNotNone(budget2.series)
        self.assertNotEqual(budget1.series.uuid, budget2.series.uuid)

        # Verify two BudgetSeries were created
        self.assertEqual(BudgetSeries.objects.count(), 2)

        # Verify each series belongs to correct user
        self.assertEqual(budget1.series.user, self.owner)
        self.assertEqual(budget2.series.user, second_user)
