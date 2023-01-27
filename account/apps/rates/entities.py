from typing import List, TypedDict


class RateItem(TypedDict):
    currency: str
    rate: str


class BatchedRateRequest(TypedDict):
    base_currency: str
    rate_date: str
    user: str
    items: List[RateItem]
