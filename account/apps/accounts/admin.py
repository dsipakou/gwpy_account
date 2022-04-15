from accounts.models import Account
from django.contrib import admin


class AccountAdmin(admin.ModelAdmin):
    list_display = ("source", "user_name", "amount", "created_at", "modified_at")

    def user_name(self, obj):
        return obj.user.username


admin.site.register(Account, AccountAdmin)
