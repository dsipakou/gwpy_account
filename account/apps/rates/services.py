from rates.entities import BatchedRateRequest
from rates.models import Rate
from currencies.models import Currency
from budget.models import Budget
from budget.services import BudgetService


class RateService:
    @classmethod
    def create_batched_rates(cls, data: BatchedRateRequest):
        currencies_qs = Currency.objects.values('code', 'uuid')
        currencies = { item['code']: str(item['uuid']) for item in currencies_qs }
        for item in data['items']:
            Rate.objects.update_or_create(
                currency_id=currencies[item['code']],
                rate_date=data['rate_date'],
                defaults={
                    'rate': item['rate'],
                    'base_currency_id': currencies[data['base_currency']],
                }
            )
        budget_uuids = Budget.objects.filter(budget_date=data['rate_date']).values_list('uuid', flat=True)
        BudgetService.create_budget_multicurrency_amount(budget_uuids)