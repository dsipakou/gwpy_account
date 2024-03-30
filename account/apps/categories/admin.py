from django import forms
from django.contrib import admin

from budget.models import Budget
from categories.models import Category


class CategoryFormAdmin(forms.ModelForm):
    class Meta:
        model = Category
        fields = "__all__"
        exclude = ("type",)


class CategoryAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "parent_name",
        "children",
        "budget",
        "type",
        "created_at",
        "modified_at",
    )

    form = CategoryFormAdmin

    def parent_name(self, obj):
        return obj.parent.name if obj.parent else None

    def children(self, obj):
        return Category.objects.filter(parent=obj).count()

    def budget(self, obj):
        return Budget.objects.filter(category=obj).count()

    def has_delete_permission(self, request, obj=None) -> bool:
        if Budget.objects.filter(category=obj).exists():
            return False
        if Category.objects.filter(parent=obj).exists():
            return False

        return super().has_delete_permission(request, obj)


admin.site.register(Category, CategoryAdmin)
