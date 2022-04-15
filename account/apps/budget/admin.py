from django.contrib import admin
from budget.models import Budget


class BudgetAdmin(admin.ModelAdmin):
    pass


admin.site.register(Budget, BudgetAdmin)
