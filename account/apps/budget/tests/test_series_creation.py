import datetime
import uuid

from django.test import TestCase

from budget.constants import BudgetDuplicateType
from budget.models import Budget, BudgetSeries
from budget.serializers import BudgetSerializer
from categories.models import Category
from currencies.models import Currency
from users.models import User
from workspaces.models import Workspace


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
        """Test that budgets without recurrent field don't create a BudgetSeries"""
        today = datetime.date.today()

        data = {
            "user": self.owner.uuid,
            "category": self.category.uuid,
            "currency": self.currency.uuid,
            "title": "Car Repair",
            "amount": 500.0,
            # No recurrent field - occasional budgets don't have series
            "budget_date": today + datetime.timedelta(days=100),
        }

        serializer = BudgetSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)

        budget = serializer.save()

        # Verify no BudgetSeries was created
        self.assertIsNone(budget.series)
        self.assertEqual(BudgetSeries.objects.count(), 0)

    def test_same_title_creates_separate_budget_series(self):
        """Test that budgets with same title create SEPARATE independent series"""
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

        # Verify both budgets have SEPARATE series (not shared)
        self.assertIsNotNone(budget1.series)
        self.assertIsNotNone(budget2.series)
        self.assertNotEqual(budget1.series.uuid, budget2.series.uuid)

        # Verify TWO BudgetSeries were created
        self.assertEqual(BudgetSeries.objects.count(), 2)

        # Verify both series have correct properties
        self.assertEqual(budget1.series.title, "Weekly Groceries")
        self.assertEqual(budget2.series.title, "Weekly Groceries")
        self.assertEqual(budget1.series.frequency, BudgetSeries.Frequency.WEEKLY)
        self.assertEqual(budget2.series.frequency, BudgetSeries.Frequency.WEEKLY)

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

        # Create MONTHLY budget with same title but different date to avoid unique constraint
        data2 = {
            "user": self.owner.uuid,
            "category": self.category.uuid,
            "currency": self.currency.uuid,
            "title": "Fuel",
            "amount": 400.0,
            "recurrent": BudgetDuplicateType.MONTHLY.value,
            "budget_date": today + datetime.timedelta(days=1),
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
            "budget_date": today + datetime.timedelta(days=150),
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
            "budget_date": today + datetime.timedelta(days=250),
        }

        serializer = BudgetSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)

        budget = serializer.save()

        # Verify series has correct category and currency
        self.assertEqual(budget.series.category.uuid, food_category.uuid)
        self.assertEqual(budget.series.currency.uuid, self.currency.uuid)

    def test_multiple_users_with_same_title_create_separate_series(self):
        """Test that different users with same budget title get separate BudgetSeries"""
        # Create second user with unique email
        second_user = User.objects.create_user(
            username="seconduser", email="seconduser@test.com", password="testpassword"
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
            "budget_date": today + datetime.timedelta(days=200),
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
            "budget_date": today + datetime.timedelta(days=200),
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

    def test_multiple_same_title_budgets_independent_series(self):
        """Test that multiple budgets with same title have independent lifecycles"""
        today = datetime.date.today()

        # Create two "Weekly Groceries" budgets at different dates
        data1 = {
            "user": self.owner.uuid,
            "category": self.category.uuid,
            "currency": self.currency.uuid,
            "title": "Weekly Groceries",
            "amount": 100.0,
            "recurrent": BudgetDuplicateType.WEEKLY.value,
            "budget_date": today,
        }

        serializer1 = BudgetSerializer(data=data1)
        self.assertTrue(serializer1.is_valid(), serializer1.errors)
        budget1 = serializer1.save()

        data2 = {
            "user": self.owner.uuid,
            "category": self.category.uuid,
            "currency": self.currency.uuid,
            "title": "Weekly Groceries",
            "amount": 120.0,
            "recurrent": BudgetDuplicateType.WEEKLY.value,
            "budget_date": today + datetime.timedelta(days=30),
        }

        serializer2 = BudgetSerializer(data=data2)
        self.assertTrue(serializer2.is_valid(), serializer2.errors)
        budget2 = serializer2.save()

        series1 = budget1.series
        series2 = budget2.series

        # Verify they're separate series
        self.assertIsNotNone(series1)
        self.assertIsNotNone(series2)
        self.assertNotEqual(series1.uuid, series2.uuid)
        self.assertEqual(BudgetSeries.objects.count(), 2)

        # Stop series1 by setting until date
        series1.until = today + datetime.timedelta(days=7)
        series1.save()

        # Verify series2 is unaffected
        series2.refresh_from_db()
        self.assertIsNone(series2.until)  # Still active

        # Verify series1 properties
        series1.refresh_from_db()
        self.assertEqual(series1.until, today + datetime.timedelta(days=7))
        self.assertEqual(series1.title, "Weekly Groceries")

        # Verify series2 properties remain unchanged
        self.assertEqual(series2.title, "Weekly Groceries")
        self.assertEqual(series2.amount, 120.0)
