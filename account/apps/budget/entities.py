import datetime
from typing import TypedDict
from uuid import UUID, uuid4

import pydantic

from budget.models import Budget
from categories.models import Category
from currencies.models import Currency
from transactions.models import Transaction


class BudgetTransactionItem(TypedDict):
    uuid: UUID
    currency: UUID
    currency_code: str
    spent_in_base_currency: float
    spent_in_original_currency: float
    spent_in_currencies: dict[str, float]
    transaction_date: str


class BudgetItem(TypedDict):
    uuid: UUID
    user: UUID
    category: UUID
    currency: UUID
    title: str
    budget_date: datetime.date
    transactions: list[BudgetTransactionItem]
    category_name: str
    description: str
    is_completed: bool
    recurrent: str
    planned: float
    planned_in_currencies: dict[str, float]
    spent_in_base_currency: float
    spent_in_original_currency: float
    spent_in_currencies: dict[str, float]
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

    @classmethod
    def init(cls, transaction: Transaction) -> "BudgetTransactionModel":
        return cls(
            uuid=transaction.uuid,
            user=transaction.user.uuid,
            currency=transaction.currency.uuid,
            currency_code=transaction.currency.code,
            spent=transaction.amount,
            transaction_date=transaction.transaction_date,
            spent_in_currencies=transaction.multicurrency_map.copy(),
        )


class BudgetModel(pydantic.BaseModel):
    uuid: UUID
    user: UUID
    category: UUID
    currency: UUID
    parent_budget: str = ""
    title: str
    budget_date: datetime.date
    transactions: list[BudgetTransactionModel] = pydantic.Field(default_factory=list)
    category_name: str
    description: str | None
    is_completed: bool
    recurrent: str | None
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
        cls, budget: Budget, available_currencies: list[Currency]
    ) -> "BudgetModel":
        return cls(
            uuid=budget.uuid,
            user=budget.user.uuid,
            category=budget.category.uuid,
            currency=budget.currency.uuid,
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

    @classmethod
    def init_for_transaction(
        cls, budget: Budget, available_currencies: list[Currency]
    ) -> "BudgetModel":
        return cls(
            uuid=budget.uuid,
            user=budget.user.uuid,
            category=budget.category.uuid,
            currency=budget.currency.uuid,
            title=budget.title,
            budget_date=budget.budget_date,
            category_name=budget.category.name,
            description=budget.description,
            is_completed=budget.is_completed,
            recurrent=budget.recurrent,
            created_at=budget.created_at,
            modified_at=budget.modified_at,
            planned=0,
            planned_in_currencies={
                currency["code"]: 0 for currency in available_currencies
            },
            spent_in_currencies={
                currency["code"]: 0 for currency in available_currencies
            },
        )

    def update_spent_values(
        self, available_currencies: list[Currency], amount: dict[str, int]
    ):
        for currency in available_currencies:
            self.spent_in_currencies[currency["code"]] = round(
                self.spent_in_currencies[currency["code"]]
                + amount.get(currency["code"], 0),
                2,
            )


class GroupedBudgetModel(pydantic.BaseModel):
    uuid: UUID = pydantic.Field(default_factory=uuid4)
    user: UUID
    title: str
    planned: float = pydantic.Field(ge=0, default=0)
    spent: float = pydantic.Field(ge=0, default=0)
    items: list[BudgetModel] = pydantic.Field(default_factory=list)
    items_map: dict[UUID, BudgetModel] = pydantic.Field(default_factory=dict)
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
                str(budget.category.uuid),
                budget.budget_date.strftime("%Y-%m"),
            ]
        )

    @classmethod
    def init(
        cls, budget: Budget, available_currencies: list[Currency]
    ) -> "GroupedBudgetModel":
        return cls(
            user=budget.user.uuid,
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

    @classmethod
    def build_for_transaction(
        cls,
        budget: Budget,
        category: Category,
        date_from: datetime.date,
        date_to: datetime.date,
        available_currencies: list[Currency],
    ) -> "GroupedBudgetModel":
        return cls(
            user=budget.user.uuid,
            title=budget.title,
            is_another_category=category.uuid != budget.category.uuid,
            is_another_month=budget.budget_date < date_from
            or budget.budget_date > date_to,
            planned=0,
            planned_in_currencies={
                currency["code"]: 0 for currency in available_currencies
            },
            spent_in_currencies={
                currency["code"]: 0 for currency in available_currencies
            },
            spent_in_currencies_overall={
                currency["code"]: 0 for currency in available_currencies
            },
        )

    def update_planned_values(
        self, available_currencies: list[Currency], amount: dict[str, int]
    ):
        for currency in available_currencies:
            self.planned_in_currencies[currency["code"]] = round(
                self.planned_in_currencies[currency["code"]]
                + amount.get(currency["code"], 0),
                2,
            )

    def update_spent_values(
        self, available_currencies: list[Currency], amount: dict[str, int]
    ):
        for currency in available_currencies:
            self.spent_in_currencies[currency["code"]] = round(
                self.spent_in_currencies[currency["code"]]
                + amount.get(currency["code"], 0),
                2,
            )

    def update_spent_overall_values(
        self, available_currencies: list[Currency], amount: dict[str, int]
    ):
        for currency in available_currencies:
            self.spent_in_currencies_overall[currency["code"]] = round(
                self.spent_in_currencies_overall[currency["code"]]
                + amount.get(currency["code"], 0),
                2,
            )


class BudgetGroupedItem(TypedDict):
    uuid: UUID
    user: UUID
    title: str
    planned: float
    planned_in_currencies: dict[str, float]
    spent_in_base_currency: float
    spent_in_original_currency: float
    spent_in_currencies: dict[str, float]
    items: list[BudgetItem]


class CategoryModel(pydantic.BaseModel):
    uuid: UUID
    category_name: str
    budgets: list[GroupedBudgetModel] = pydantic.Field(default_factory=list)
    budgets_map: dict[str, GroupedBudgetModel] = pydantic.Field(default_factory=dict)
    planned: float = pydantic.Field(ge=0, default=0)
    spent: float = pydantic.Field(ge=0, default=0)
    planned_in_currencies: dict[str, float] = pydantic.Field(default_factory=dict)
    spent_in_currencies: dict[str, float] = pydantic.Field(default_factory=dict)

    @classmethod
    def init(
        cls, category: Category, available_currencies: list[Currency]
    ) -> "CategoryModel":
        return cls(
            uuid=category.uuid,
            category_name=category.name,
            spent=0,
            spent_in_currencies={
                currency["code"]: 0 for currency in available_currencies
            },
            planned_in_currencies={
                currency["code"]: 0 for currency in available_currencies
            },
        )

    def update_planned_values(
        self, available_currencies: list[Currency], amount: dict[str, int]
    ):
        for currency in available_currencies:
            self.planned_in_currencies[currency["code"]] = round(
                self.planned_in_currencies[currency["code"]]
                + amount.get(currency["code"], 0),
                2,
            )

    def update_spent_values(
        self, available_currencies: list[Currency], amount: dict[str, int]
    ):
        for currency in available_currencies:
            self.spent_in_currencies[currency["code"]] = round(
                self.spent_in_currencies[currency["code"]]
                + amount.get(currency["code"], 0),
                2,
            )


class CategoryItem(TypedDict):
    uuid: UUID
    user: UUID
    category_name: str
    budgets: list[BudgetGroupedItem]
    planned: float
    planned_in_currencies: dict[str, float]
    spent_in_original_currency: float
    spent_in_base_currency: float
    spent_in_currencies: dict[str, float]


class MonthUsageSum(pydantic.BaseModel):
    month: datetime.date
    amount: float
