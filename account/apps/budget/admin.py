from budget.models import Budget
from django.contrib import admin


class BudgetAdmin(admin.ModelAdmin):
    list_display = ("category_name", "amount", "recurrent", "created_at", "modified_at")

    def category_name(self, obj):
        return obj.category.name


admin.site.register(Budget, BudgetAdmin)
