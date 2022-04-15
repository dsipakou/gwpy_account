from currencies.models import Currency
from django.contrib import admin


class CurrencyAdmin(admin.ModelAdmin):
    list_display = ("verbal_name", "code", "sign", "created_at", "modified_at")

    def has_delete_permission(self, request, obj=None) -> bool:
        if obj and (obj.is_base or obj.is_default):
            return False

        return super().has_delete_permission(request, obj)


admin.site.register(Currency, CurrencyAdmin)
