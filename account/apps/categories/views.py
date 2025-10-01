from budget.models import Budget
from categories.models import Category
from categories.serializers import (
    CategoryReassignSerializer,
    CategoryReorderSerializer,
    CategorySerializer,
)
from django.db.models.deletion import transaction
from rest_framework.exceptions import ValidationError, status
from rest_framework.generics import (
    CreateAPIView,
    ListCreateAPIView,
    RetrieveUpdateDestroyAPIView,
)
from rest_framework.mixins import Response
from transactions.models import Transaction
from workspaces.filters import FilterByWorkspace
from workspaces.permissions import BaseWorkspacePermission

from account.apps.categories.services import CategoryService


class CategoryList(ListCreateAPIView):
    queryset = (
        Category.objects.all().select_related("parent").order_by("position", "name")
    )
    serializer_class = CategorySerializer
    permission_classes = (BaseWorkspacePermission,)
    filter_backends = (FilterByWorkspace,)

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
    permission_classes = (BaseWorkspacePermission,)
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
        if Transaction.objects.filter(category=instance).exists():
            raise ValidationError(
                "Cannot delete category. There are transactions assigned"
            )
        super().perform_destroy(instance)


class CategoryReassignView(CreateAPIView):
    queryset = Category.objects.all()
    serializer_class = CategoryReassignSerializer
    permission_classes = (BaseWorkspacePermission,)
    lookup_field = "uuid"

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid()
        source_category_uuid = kwargs.get("uuid")
        dest_category_uuid = serializer.validated_data["category"]
        if source_category_uuid == dest_category_uuid:
            raise ValidationError("Cannot reassign to the same category")

        source_category = Category.objects.get(uuid=source_category_uuid)
        dest_category = Category.objects.get(uuid=dest_category_uuid)
        transactions = Transaction.objects.filter(category__uuid=source_category_uuid)
        budgets = Budget.objects.filter(category__uuid=source_category.parent.uuid)
        with transaction.atomic():
            transactions.update(category=dest_category.uuid)
            budgets.update(category=dest_category.parent.uuid)
        return Response(status=status.HTTP_200_OK)


class CategoryReorderView(CreateAPIView):
    queryset = Category.objects.all()
    serializer_class = CategoryReorderSerializer
    permission_classes = (BaseWorkspacePermission,)
    lookup_field = "uuid"

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid()
        target_category_uuid = serializer.validated_data["category"]
        new_index = serializer.validated_data["index"]
        CategoryService.reorder_categories(target_category_uuid, new_index)
        return Response(status=status.HTTP_200_OK)
