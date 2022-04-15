from categories.models import Category
from rest_framework import serializers


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = (
            "uuid",
            "name",
            "parent",
            "is_income",
            "created_at",
            "modified_at",
        )

    def validate(self, data):
        name = data.get("name")
        parent = data.get("parent")

        if parent is None and Category.objects.filter(name=name).exists():
            raise serializers.ValidationError(
                "Parent category with this name already exists"
            )

        return super().validate(data)
