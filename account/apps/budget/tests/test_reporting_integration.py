"""Integration tests for budget reporting (load_budget_v2).

These tests verify the monthly budget reporting workflow with real database
operations, ensuring correct aggregation of budgets, transactions, and
multi-currency conversions.
"""

import datetime
import uuid

from django.test import TestCase

from accounts.models import Account
from budget.models import Budget, BudgetMulticurrency, BudgetSeries
from budget.services import BudgetService
from categories.models import Category
from currencies.models import Currency
from rates.models import Rate
from transactions.models import Transaction, TransactionMulticurrency
from users.models import User
from workspaces.models import Workspace


class TestLoadBudgetV2Integration(TestCase):
    """Integration tests for load_budget_v2 monthly reporting."""

    @classmethod
    def setUpTestData(cls):
        """Set up test workspace, users, currencies, and categories."""
        cls.owner = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpassword"
        )
        cls.workspace = Workspace.objects.create(name="Test Workspace", owner=cls.owner)
        cls.owner.active_workspace = cls.workspace
        cls.owner.save()

        # Create currencies
        cls.usd = Currency.objects.create(
            code="USD", sign="$", is_base=True, workspace=cls.workspace
        )
        cls.eur = Currency.objects.create(
            code="EUR", sign="€", is_base=False, workspace=cls.workspace
        )
        cls.gbp = Currency.objects.create(
            code="GBP", sign="£", is_base=False, workspace=cls.workspace
        )

        # Create exchange rates (rates are relative to base currency USD)
        cls.today = datetime.date.today()
        Rate.objects.create(
            currency=cls.usd,
            base_currency=cls.usd,
            rate_date=cls.today,
            rate=1.0,
            workspace=cls.workspace,
        )
        Rate.objects.create(
            currency=cls.eur,
            base_currency=cls.usd,
            rate_date=cls.today,
            rate=0.85,
            workspace=cls.workspace,
        )
        Rate.objects.create(
            currency=cls.gbp,
            base_currency=cls.usd,
            rate_date=cls.today,
            rate=0.73,
            workspace=cls.workspace,
        )

        # Create parent categories
        cls.food_category = Category.objects.create(
            uuid=uuid.uuid4(),
            name="Food",
            type="EXP",
            workspace=cls.workspace,
            parent=None,
            position=0,
        )
        cls.transport_category = Category.objects.create(
            uuid=uuid.uuid4(),
            name="Transport",
            type="EXP",
            workspace=cls.workspace,
            parent=None,
            position=1,
        )

        # Create subcategories
        cls.groceries_category = Category.objects.create(
            uuid=uuid.uuid4(),
            name="Groceries",
            type="EXP",
            workspace=cls.workspace,
            parent=cls.food_category,
            position=0,
        )
        cls.restaurants_category = Category.objects.create(
            uuid=uuid.uuid4(),
            name="Restaurants",
            type="EXP",
            workspace=cls.workspace,
            parent=cls.food_category,
            position=1,
        )

        # Create account for transactions
        cls.account = Account.objects.create(
            uuid=uuid.uuid4(),
            title="Test Account",
            description="Test account",
            is_main=True,
            user=cls.owner,
            workspace=cls.workspace,
            category=cls.food_category,
        )

    def setUp(self):
        """Clean up budgets and transactions before each test."""
        Budget.objects.all().delete()
        Transaction.objects.all().delete()
        BudgetSeries.objects.all().delete()

    def test_load_budget_v2_with_budgets_and_transactions(self):
        """Test complete workflow with budgets and transactions."""
        # Create budgets for current month
        first_day = self.today.replace(day=1)
        last_day = (first_day + datetime.timedelta(days=32)).replace(
            day=1
        ) - datetime.timedelta(days=1)

        # Create food budget
        food_budget = Budget.objects.create(
            uuid=uuid.uuid4(),
            user=self.owner,
            workspace=self.workspace,
            category=self.food_category,
            currency=self.usd,
            title="Monthly Food",
            amount=500.0,
            budget_date=first_day,
        )
        BudgetMulticurrency.objects.create(
            budget=food_budget,
            amount_map={"USD": 500.0, "EUR": 425.0, "GBP": 365.0},
        )

        # Create transport budget
        transport_budget = Budget.objects.create(
            uuid=uuid.uuid4(),
            user=self.owner,
            workspace=self.workspace,
            category=self.transport_category,
            currency=self.usd,
            title="Transport",
            amount=200.0,
            budget_date=first_day,
        )
        BudgetMulticurrency.objects.create(
            budget=transport_budget,
            amount_map={"USD": 200.0, "EUR": 170.0, "GBP": 146.0},
        )

        # Create transactions
        grocery_transaction = Transaction.objects.create(
            uuid=uuid.uuid4(),
            user=self.owner,
            workspace=self.workspace,
            account=self.account,
            category=self.groceries_category,
            currency=self.usd,
            amount=150.0,
            transaction_date=first_day + datetime.timedelta(days=5),
            budget=food_budget,
        )
        TransactionMulticurrency.objects.create(
            transaction=grocery_transaction,
            amount_map={"USD": 150.0, "EUR": 127.5, "GBP": 109.5},
        )

        restaurant_transaction = Transaction.objects.create(
            uuid=uuid.uuid4(),
            user=self.owner,
            workspace=self.workspace,
            account=self.account,
            category=self.restaurants_category,
            currency=self.usd,
            amount=80.0,
            transaction_date=first_day + datetime.timedelta(days=10),
            budget=food_budget,
        )
        TransactionMulticurrency.objects.create(
            transaction=restaurant_transaction,
            amount_map={"USD": 80.0, "EUR": 68.0, "GBP": 58.4},
        )

        # Run load_budget_v2
        result = BudgetService.load_budget_v2(
            workspace=self.workspace,
            budgets_qs=Budget.objects.filter(workspace=self.workspace),
            categories_qs=Category.objects.filter(workspace=self.workspace),
            currencies_qs=Currency.objects.filter(workspace=self.workspace),
            transactions_qs=Transaction.objects.filter(workspace=self.workspace),
            date_from=first_day.isoformat(),
            date_to=last_day.isoformat(),
            user=None,
        )

        # Verify results
        self.assertEqual(len(result), 2)  # 2 parent categories

        # Find food category in results
        food_result = next(
            (cat for cat in result if cat["category_name"] == "Food"), None
        )
        self.assertIsNotNone(food_result)
        self.assertEqual(food_result["planned"], 500.0)
        self.assertEqual(food_result["spent"], 230.0)  # 150 + 80

        # Verify budgets in food category
        self.assertEqual(len(food_result["budgets"]), 1)
        food_budget_group = food_result["budgets"][0]
        self.assertEqual(food_budget_group["title"], "Monthly Food")
        self.assertEqual(food_budget_group["planned"], 500.0)
        self.assertEqual(food_budget_group["spent"], 230.0)

        # Verify transactions are included
        self.assertEqual(len(food_budget_group["items"]), 1)
        budget_item = food_budget_group["items"][0]
        self.assertEqual(len(budget_item["transactions"]), 2)

    def test_load_budget_v2_no_budgets(self):
        """Test reporting with no budgets (edge case)."""
        first_day = self.today.replace(day=1)
        last_day = (first_day + datetime.timedelta(days=32)).replace(
            day=1
        ) - datetime.timedelta(days=1)

        result = BudgetService.load_budget_v2(
            workspace=self.workspace,
            budgets_qs=Budget.objects.filter(workspace=self.workspace),
            categories_qs=Category.objects.filter(workspace=self.workspace),
            currencies_qs=Currency.objects.filter(workspace=self.workspace),
            transactions_qs=Transaction.objects.filter(workspace=self.workspace),
            date_from=first_day.isoformat(),
            date_to=last_day.isoformat(),
            user=None,
        )

        # Should return categories but with no budgets
        self.assertEqual(len(result), 2)  # Still have categories
        for category in result:
            self.assertEqual(len(category["budgets"]), 0)
            self.assertEqual(category["planned"], 0.0)
            self.assertEqual(category["spent"], 0.0)

    def test_load_budget_v2_no_transactions(self):
        """Test reporting with budgets but no transactions."""
        first_day = self.today.replace(day=1)
        last_day = (first_day + datetime.timedelta(days=32)).replace(
            day=1
        ) - datetime.timedelta(days=1)

        # Create budget without transactions
        food_budget = Budget.objects.create(
            uuid=uuid.uuid4(),
            user=self.owner,
            workspace=self.workspace,
            category=self.food_category,
            currency=self.usd,
            title="Monthly Food",
            amount=500.0,
            budget_date=first_day,
        )
        BudgetMulticurrency.objects.create(
            budget=food_budget,
            amount_map={"USD": 500.0, "EUR": 425.0, "GBP": 365.0},
        )

        result = BudgetService.load_budget_v2(
            workspace=self.workspace,
            budgets_qs=Budget.objects.filter(workspace=self.workspace),
            categories_qs=Category.objects.filter(workspace=self.workspace),
            currencies_qs=Currency.objects.filter(workspace=self.workspace),
            transactions_qs=Transaction.objects.filter(workspace=self.workspace),
            date_from=first_day.isoformat(),
            date_to=last_day.isoformat(),
            user=None,
        )

        # Find food category
        food_result = next(
            (cat for cat in result if cat["category_name"] == "Food"), None
        )
        self.assertIsNotNone(food_result)
        self.assertEqual(food_result["planned"], 500.0)
        self.assertEqual(food_result["spent"], 0.0)  # No spending

        # Verify budget exists but has no transactions
        budget_item = food_result["budgets"][0]["items"][0]
        self.assertEqual(len(budget_item["transactions"]), 0)

    def test_load_budget_v2_multi_currency(self):
        """Test multi-currency calculations."""
        first_day = self.today.replace(day=1)
        last_day = (first_day + datetime.timedelta(days=32)).replace(
            day=1
        ) - datetime.timedelta(days=1)

        # Create budget in EUR
        food_budget = Budget.objects.create(
            uuid=uuid.uuid4(),
            user=self.owner,
            workspace=self.workspace,
            category=self.food_category,
            currency=self.eur,
            title="Food EUR",
            amount=425.0,  # ~500 USD
            budget_date=first_day,
        )
        BudgetMulticurrency.objects.create(
            budget=food_budget,
            amount_map={"USD": 500.0, "EUR": 425.0, "GBP": 365.0},
        )

        # Create transaction in GBP
        transaction = Transaction.objects.create(
            uuid=uuid.uuid4(),
            user=self.owner,
            workspace=self.workspace,
            account=self.account,
            category=self.groceries_category,
            currency=self.gbp,
            amount=109.5,  # ~150 USD
            transaction_date=first_day + datetime.timedelta(days=5),
            budget=food_budget,
        )
        TransactionMulticurrency.objects.create(
            transaction=transaction,
            amount_map={"USD": 150.0, "EUR": 127.5, "GBP": 109.5},
        )

        result = BudgetService.load_budget_v2(
            workspace=self.workspace,
            budgets_qs=Budget.objects.filter(workspace=self.workspace),
            categories_qs=Category.objects.filter(workspace=self.workspace),
            currencies_qs=Currency.objects.filter(workspace=self.workspace),
            transactions_qs=Transaction.objects.filter(workspace=self.workspace),
            date_from=first_day.isoformat(),
            date_to=last_day.isoformat(),
            user=None,
        )

        # Verify multi-currency conversions
        food_result = next(
            (cat for cat in result if cat["category_name"] == "Food"), None
        )
        self.assertIsNotNone(food_result)

        # Check planned amounts in different currencies
        planned_currencies = food_result["planned_in_currencies"]
        self.assertAlmostEqual(planned_currencies["USD"], 500.0, places=1)
        self.assertAlmostEqual(planned_currencies["EUR"], 425.0, places=1)
        self.assertAlmostEqual(planned_currencies["GBP"], 365.0, places=1)

        # Check spent amounts in different currencies
        spent_currencies = food_result["spent_in_currencies"]
        self.assertAlmostEqual(spent_currencies["USD"], 150.0, places=1)
        self.assertAlmostEqual(spent_currencies["EUR"], 127.5, places=1)
        self.assertAlmostEqual(spent_currencies["GBP"], 109.5, places=1)

    def test_load_budget_v2_user_filter(self):
        """Test filtering by specific user."""
        first_day = self.today.replace(day=1)
        last_day = (first_day + datetime.timedelta(days=32)).replace(
            day=1
        ) - datetime.timedelta(days=1)

        # Create second user
        second_user = User.objects.create_user(
            username="seconduser", email="second@example.com", password="testpass"
        )
        second_user.active_workspace = self.workspace
        second_user.save()

        # Create budgets for both users
        owner_budget = Budget.objects.create(
            uuid=uuid.uuid4(),
            user=self.owner,
            workspace=self.workspace,
            category=self.food_category,
            currency=self.usd,
            title="Owner Food",
            amount=500.0,
            budget_date=first_day,
        )
        second_budget = Budget.objects.create(
            uuid=uuid.uuid4(),
            user=second_user,
            workspace=self.workspace,
            category=self.food_category,
            currency=self.usd,
            title="Second User Food",
            amount=300.0,
            budget_date=first_day,
        )

        # Filter by owner only
        result = BudgetService.load_budget_v2(
            workspace=self.workspace,
            budgets_qs=Budget.objects.filter(workspace=self.workspace),
            categories_qs=Category.objects.filter(workspace=self.workspace),
            currencies_qs=Currency.objects.filter(workspace=self.workspace),
            transactions_qs=Transaction.objects.filter(workspace=self.workspace),
            date_from=first_day.isoformat(),
            date_to=last_day.isoformat(),
            user=str(self.owner.uuid),
        )

        # Verify only owner's budget appears
        food_result = next(
            (cat for cat in result if cat["category_name"] == "Food"), None
        )
        self.assertEqual(food_result["planned"], 500.0)
        self.assertEqual(len(food_result["budgets"]), 1)
        self.assertEqual(food_result["budgets"][0]["title"], "Owner Food")

    def test_load_budget_v2_with_budget_series(self):
        """Test integration with BudgetSeries materialization."""
        first_day = self.today.replace(day=1)
        last_day = (first_day + datetime.timedelta(days=32)).replace(
            day=1
        ) - datetime.timedelta(days=1)

        # Create budget series
        series = BudgetSeries.objects.create(
            uuid=uuid.uuid4(),
            user=self.owner,
            workspace=self.workspace,
            category=self.food_category,
            currency=self.usd,
            title="Monthly Food Series",
            amount=500.0,
            frequency="MONTHLY",
            interval=1,
            start_date=first_day,
            until=None,
        )

        # Call load_budget_v2 (should trigger materialization)
        result = BudgetService.load_budget_v2(
            workspace=self.workspace,
            budgets_qs=Budget.objects.filter(workspace=self.workspace),
            categories_qs=Category.objects.filter(workspace=self.workspace),
            currencies_qs=Currency.objects.filter(workspace=self.workspace),
            transactions_qs=Transaction.objects.filter(workspace=self.workspace),
            date_from=first_day.isoformat(),
            date_to=last_day.isoformat(),
            user=None,
        )

        # Verify budget was materialized
        materialized_budgets = Budget.objects.filter(series=series)
        self.assertGreaterEqual(materialized_budgets.count(), 1)

        # Verify it appears in results
        food_result = next(
            (cat for cat in result if cat["category_name"] == "Food"), None
        )
        self.assertIsNotNone(food_result)
        self.assertEqual(len(food_result["budgets"]), 1)
