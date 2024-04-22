from rest_framework import serializers

from categories.models import Category


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = (
            "uuid",
            "icon",
            "name",
            "parent",
            "type",
            "description",
            "created_at",
            "modified_at",
        )

    def validate(self, attrs):
        name = attrs.get("name")
        parent = attrs.get("parent")

        if name and parent is None and Category.objects.filter(name=name).exists():
            raise serializers.ValidationError(
                "Parent category with this name already exists"
            )

        return super().validate(attrs)

    def create(self, validated_data):
        user = self.context["request"].user
        return Category.objects.create(
            workspace=user.active_workspace,
            **validated_data,
        )


class CategoryReassignSerializer(serializers.Serializer):
    category = serializers.UUIDField()

    def validate(self, attrs):
        category = attrs.get("category")
        if not Category.objects.filter(uuid=category).exists():
            raise serializers.ValidationError("Destinated category does not exists")

        return super().validate(attrs)
