from django.contrib import admin
from rates.models import Rate

from currencies.models import Currency


class CurrencyAdmin(admin.ModelAdmin):
    list_display = ("verbal_name", "code", "sign", "created_at", "modified_at")

    def has_delete_permission(self, request, obj=None) -> bool:
        if obj and (obj.is_base or obj.is_default):
            return False

        if Rate.objects.filter(currency=obj).exists():
            return False

        return super().has_delete_permission(request, obj)


admin.site.register(Currency, CurrencyAdmin)
