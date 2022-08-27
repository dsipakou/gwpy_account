from typing import TypedDict, List

class RateItem(TypedDict):
    currency: str
    rate: str

class BatchedRateRequest(TypedDict):
    base_currency: str
    rate_date: str
    items: List[RateItem]