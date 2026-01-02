from datetime import date
from typing import TypedDict

from pydantic import BaseModel


class RateItem(TypedDict):
    currency: str
    rate: str


class BatchedRateRequest(TypedDict):
    base_currency: str
    rate_date: str
    user: str
    items: list[RateItem]


class RateOnDate(BaseModel):
    currency_code: str
    rate: float
    rate_date: date
