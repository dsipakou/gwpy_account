from budget.models import Budget
from categories.models import Category
from categories.serializers import CategorySerializer
from rest_framework.exceptions import ValidationError
from rest_framework.generics import ListCreateAPIView, RetrieveUpdateDestroyAPIView


class CategoryList(ListCreateAPIView):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer

    def perform_create(self, serializer):
        """Check if parent category is not a child of any other category

        Raises:
            ValidationError: if parent category is already a child category
        """

        if (
            serializer.validated_data["parent"]
            and serializer.validated_data["parent"].parent is not None
        ):
            raise ValidationError("Child category cannot by parent category")
        super().perform_create(serializer)


class CategoryDetails(RetrieveUpdateDestroyAPIView):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    lookup_field = "uuid"

    def perform_update(self, serializer):
        """Two checks:
        - Child category cannot be parent
        - Instance with childs cannot become child category

        Raises:
            ValidationError: if parent category is already a child category
            ValidationError: when instance with at least one child converted to child category
        """

        if (
            serializer.validated_data.get("parent")
            and serializer.validated_data["parent"].parent is not None
        ):
            raise ValidationError("Child category cannot by parent category")
        if serializer.validated_data.get("parent") is not None:
            if Category.objects.filter(parent=serializer.instance).exists():
                raise ValidationError(
                    "This category has childs. Cannot convert to child category"
                )

        super().perform_update(serializer)

    def perform_destroy(self, instance):
        """Two checks:
         - Check if instance has childs
         - Check if instance has no correspoding budgets

        Raises:
            ValidationError: When instance has childs
        """

        if Category.objects.filter(parent=instance).exists():
            raise ValidationError("Cannot delete non empty parent category")
        if Budget.objects.filter(category=instance).exists():
            raise ValidationError("Cannot delete category. There are budgets assigned")
        super().perform_destroy(instance)
