from django.contrib import admin

from accounts.models import Account


class AccountAdmin(admin.ModelAdmin):
    list_display = ("title", "user_name", "created_at", "modified_at")

    def user_name(self, obj):
        return obj.user.username


admin.site.register(Account, AccountAdmin)
