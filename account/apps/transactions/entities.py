import datetime
from typing import Dict, List, TypedDict
from uuid import UUID


class TransactionCategoryDetails(TypedDict):
    name: str
    parent: UUID
    parent_name: str


class TransactionAccountDetails(TypedDict):
    source: str


class TransactionCurrencyDetails(TypedDict):
    sign: str


class TransactionSpentInCurrencyDetails(TypedDict):
    amount: float
    sign: str
    currency: UUID


class TransactionBudgetDetails(TypedDict):
    title: str


class TransactionItem(TypedDict):
    uuid: UUID
    user: UUID
    category: UUID
    category_details: TransactionCategoryDetails
    budget: UUID
    currency: UUID
    currency_details: TransactionCurrencyDetails
    amount: float
    spent_in_base_currency: float
    spent_in_currencies: Dict[str, float]
    account: UUID
    account_details: TransactionAccountDetails
    description: str
    transaction_date: datetime.date
    created_at: datetime.datetime
    modified_at: datetime.datetime


class GroupedByCategory(TypedDict):
    category_name: str
    parent_name: str
    spent_in_base_currency: float
    spent_in_currencies: Dict[str, TransactionSpentInCurrencyDetails]
    items: List[TransactionItem]


class GroupedByMonth(TypedDict):
    month: str
    year: str
    spent_in_base_currency: float
    spent_in_all_currencies: Dict[str, TransactionSpentInCurrencyDetails]
    items: List[TransactionItem]


class GroupedByParent(TypedDict):
    category_name: str
    spent_in_base_currency: float
    spent_in_currencies: Dict[str, TransactionSpentInCurrencyDetails]
    items: List[GroupedByCategory]
