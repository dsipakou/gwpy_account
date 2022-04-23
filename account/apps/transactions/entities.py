import datetime
from typing import TypedDict
from uuid import UUID


class TransactionCategoryDetails(TypedDict):
    name: str
    parent: UUID
    parent_name: str


class TransactionAccountDetails(TypedDict):
    source: str


class TransactionItem(TypedDict):
    uuid: UUID
    user: UUID
    category: UUID
    category_details: TransactionCategoryDetails
    budget: UUID
    currency: UUID
    amount: float
    spent_in_base_currency: float
    account: UUID
    account_details: TransactionAccountDetails
    description: str
    transaction_date: datetime.date
    created_at: datetime.datetime
    modified_at: datetime.datetime
