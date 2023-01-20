from categories.models import Category
from rest_framework import serializers


class CategorySerializer(serializers.ModelSerializer):
    test = serializers.BooleanField(required=False)

    class Meta:
        model = Category
        fields = (
            "uuid",
            "name",
            "parent",
            "type",
            "created_at",
            "modified_at",
            "test",
        )

    def validate(self, data):
        name = data.get("name")
        parent = data.get("parent")

        if parent is None and Category.objects.filter(name=name).exists():
            raise serializers.ValidationError(
                "Parent category with this name already exists"
            )

        return super().validate(data)

    def create(self, validated_data):
        user = self.context["request"].user
        return Category.objects.create(
            workspace=user.active_workspace,
            **validated_data,
        )
