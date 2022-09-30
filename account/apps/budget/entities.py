import datetime
from typing import Dict, List, TypedDict
from uuid import UUID


class BudgetTransactionItem(TypedDict):
    uuid: UUID
    currency: UUID
    currency_code: str
    spent_in_base_currency: float
    spent_in_original_currency: float
    spent_in_currencies: Dict[str, float]


class BudgetItem(TypedDict):
    uuid: UUID
    user: UUID
    category: UUID
    currency: UUID
    title: str
    budget_date: datetime.date
    transactions: List[BudgetTransactionItem]
    category_name: str
    description: str
    is_completed: bool
    recurrent: str
    planned: float
    planned_in_currencies: Dict[str, float]
    spent_in_base_currency: float
    spent_in_original_currency: float
    spent_in_currencies: Dict[str, float]
    created_at: datetime.datetime
    modified_at: datetime.datetime


class BudgetGroupedItem(TypedDict):
    uuid: UUID
    user: UUID
    title: str
    planned: float
    planned_in_currencies: Dict[str, float]
    spent_in_base_currency: float
    spent_in_original_currency: float
    spent_in_currencies: Dict[str, float]
    items: List[BudgetItem]


class CategoryItem(TypedDict):
    uuid: UUID
    user: UUID
    category_name: str
    budgets: List[BudgetGroupedItem]
    planned: float
    planned_in_currencies: Dict[str, float]
    spent_in_original_currency: float
    spent_in_base_currency: float
    spent_in_currencies: Dict[str, float]


class MonthUsageSum(TypedDict):
    month: datetime.date
    planned: float
