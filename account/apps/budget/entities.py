import datetime
from typing import Dict, List, Optional, TypedDict
from uuid import UUID, uuid4
from currencies.models import Currency
from budget.models import Budget

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
    parent_budget: str = ""
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

    class Config:
        from_attributes = True

    @classmethod
    def init(
        cls, budget: Budget, available_currencies: List[Currency]
    ) -> "BudgetModel":
        return cls(
            uuid=budget.uuid,
            user=budget.user.uuid,
            category=budget.category.uuid,
            currency=budget.currency.uuid,
            parent_budget=GroupedBudgetModel.get_grouped_budget_key(budget),
            title=budget.title,
            budget_date=budget.budget_date,
            category_name=budget.category.name,
            description=budget.description,
            is_completed=budget.is_completed,
            recurrent=budget.recurrent,
            planned=budget.amount,
            planned_in_currencies={
                currency["code"]: budget.multicurrency_map.get(currency["code"], 0)
                for currency in available_currencies
            },
            spent_in_currencies={
                currency["code"]: 0 for currency in available_currencies
            },
            created_at=budget.created_at,
            modified_at=budget.modified_at,
        )


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
    spent_in_currencies_overall: dict = pydantic.Field(default_factory=dict)

    class Config:
        from_attributes = True

    @staticmethod
    def get_grouped_budget_key(budget: BudgetModel) -> str:
        return "_".join(
            [
                budget.title,
                str(budget.category),
                budget.budget_date.strftime("%Y-%m"),
            ]
        )

    @classmethod
    def init(
        cls, budget: BudgetModel, available_currencies: List[Currency]
    ) -> "GroupedBudgetModel":
        return cls(
            user=budget.user,
            category=budget.category,
            title=budget.title,
            spent=0,
            spent_in_currencies={
                currency["code"]: 0 for currency in available_currencies
            },
            planned_in_currencies={
                currency["code"]: 0 for currency in available_currencies
            },
            spent_in_currencies_overall={
                currency["code"]: 0 for currency in available_currencies
            },
        )


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
