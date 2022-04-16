from currencies.models import Currency
from django.contrib import admin
from rates.models import Rate
from this import d


class RateAdmin(admin.ModelAdmin):
    list_display = ("currency_name", "rate", "created_at", "modified_at")

    def currency_name(self, obj):
        return Currency.objects.get(uuid=obj.currency.uuid).code


admin.site.register(Rate, RateAdmin)
