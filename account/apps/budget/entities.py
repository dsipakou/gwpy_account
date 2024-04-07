import datetime
from typing import Dict, List, Optional, TypedDict
from uuid import UUID, uuid4

import pydantic


class BudgetTransactionItem(TypedDict):
    uuid: UUID
    currency: UUID
    currency_code: str
    spent_in_base_currency: float
    spent_in_original_currency: float
    spent_in_currencies: Dict[str, float]
    transaction_date: str


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


class BudgetTransactionModel(pydantic.BaseModel):
    uuid: UUID
    user: UUID
    currency: UUID
    currency_code: str
    spent: float
    spent_in_currencies: dict[str, float] = pydantic.Field(default_factory=dict)
    transaction_date: datetime.date


class BudgetModel(pydantic.BaseModel):
    uuid: UUID
    user: UUID
    category: UUID
    currency: UUID
    title: str
    budget_date: datetime.date
    transactions: List[BudgetTransactionModel] = pydantic.Field(default_factory=list)
    category_name: str
    description: Optional[str]
    is_completed: bool
    recurrent: Optional[str]
    planned: float = pydantic.Field(ge=0, default=0)
    spent: float = pydantic.Field(ge=0, default=0)
    planned_in_currencies: dict[str, float] = pydantic.Field(default_factory=dict)
    spent_in_currencies: dict[str, float] = pydantic.Field(default_factory=dict)
    created_at: datetime.datetime
    modified_at: datetime.datetime


class GroupedBudgetModel(pydantic.BaseModel):
    uuid: UUID = pydantic.Field(default_factory=uuid4)
    user: UUID
    title: str
    planned: float = pydantic.Field(ge=0, default=0)
    spent: float = pydantic.Field(ge=0, default=0)
    items: list[BudgetModel] = pydantic.Field(default_factory=list)
    is_another_category: bool = pydantic.Field(default=False)
    is_another_month: bool = pydantic.Field(default=False)
    planned_in_currencies: dict = pydantic.Field(default_factory=dict)
    spent_in_currencies: dict = pydantic.Field(default_factory=dict)


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


class CategoryModel(pydantic.BaseModel):
    uuid: UUID
    category_name: str
    budgets: List[GroupedBudgetModel] = pydantic.Field(default_factory=list)
    planned: float = pydantic.Field(ge=0, default=0)
    spent: float = pydantic.Field(ge=0, default=0)
    planned_in_currencies: dict[str, float] = pydantic.Field(default_factory=dict)
    spent_in_currencies: dict[str, float] = pydantic.Field(default_factory=dict)


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


class MonthUsageSum(pydantic.BaseModel):
    month: datetime.date
    amount: float
