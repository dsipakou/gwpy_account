import datetime
from typing import List, TypedDict
from uuid import UUID


class BudgetTransactionItem(TypedDict):
    uuid: UUID
    currency: UUID
    currency_code: str
    spent_in_base_currency: float
    spent_in_original_currency: float


class BudgetItem(TypedDict):
    uuid: UUID
    category: UUID
    title: str
    budget_date: datetime.date
    transactions: List[BudgetTransactionItem]
    category_name: str
    description: str
    is_completed: bool
    recurrent: str
    planned: float
    spent_in_base_currency: float
    spent_in_original_currency: float
    created_at: datetime.datetime
    modified_at: datetime.datetime


class BudgetGroupedItem(TypedDict):
    uuid: UUID
    title: str
    planned: float
    spent_in_base_currency: float
    spent_in_original_currency: float
    items: List[BudgetItem]


class CategoryItem(TypedDict):
    uuid: UUID
    category_name: str
    budgets: List[BudgetGroupedItem]
    planned: float
    spent_in_original_currency: float
    spent_in_base_currency: float


class MonthUsageSum(TypedDict):
    month: datetime.date
    planned: float
