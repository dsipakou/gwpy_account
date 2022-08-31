import datetime
from typing import Dict, List, Union

from budget.models import Budget
from rates.models import Rate
from transactions.models import Transaction


def generate_date_seq(days_count):
    return [
        datetime.date.today() - datetime.timedelta(days=x) for x in range(days_count)
    ]


def generate_amount_map(
    instance: Union[Transaction, Budget], rates: List[Rate]
) -> Dict[str, int]:
    amount_mapping = {}
    for rate in rates:
        if instance.currency == rate.currency:
            # current rate currency and instance currency are the same no need to modify amount
            amount = instance.amount
        elif instance.currency == rate.base_currency:
            # instance currency is base currency so just divide - no need to convert to base currency beforehand
            amount = round(instance.amount / rate.rate, 5)
        else:
            # need to convert amount to base currency first than to current rate currency
            current_rate = rates.get(currency=instance.currency)
            amount = round(instance.amount * current_rate.rate / rate.rate, 5)
        amount_mapping[rate.currency.code] = amount
    # Create a record for base currency as well
    if rates:
        if instance.currency == rates[0].base_currency:
            amount_mapping[instance.currency.code] = instance.amount
        else:
            amount = instance.amount * rates.get(currency=instance.currency).rate
            amount_mapping[rates[0].base_currency.code] = round(amount, 5)
    return amount_mapping
