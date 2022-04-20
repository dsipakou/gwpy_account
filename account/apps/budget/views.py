import datetime

from budget.models import Budget
from budget.serializers import BudgetSerializer, PlannedBudgetSerializer
from rest_framework.exceptions import ValidationError
from rest_framework.generics import (ListAPIView, ListCreateAPIView,
                                     RetrieveUpdateDestroyAPIView)
from rest_framework.response import Response


class BudgetList(ListCreateAPIView):
    queryset = Budget.objects.all()
    serializer_class = BudgetSerializer

    def perform_create(self, serializer):
        """Check if category is parent category

        Raises:
            ValidationError: when category is not parent category
        """

        if serializer.validated_data["category"].parent is not None:
            raise ValidationError("Only parent categories can be used for budgets.")
        super().perform_create(serializer)


class BudgetDetails(RetrieveUpdateDestroyAPIView):
    queryset = Budget.objects.all()
    serializer_class = BudgetSerializer
    lookup_field = "uuid"

    def perform_update(self, serializer):
        """Check if category is parent category

        Raises:
            ValidationError: when category is not parent category
        """

        if serializer.validated_data["category"].parent is not None:
            raise ValidationError("Only parent categories can be used for budgets.")
        super().perform_update(serializer)


class PlannedBudgetList(ListAPIView):
    queryset = Budget.objects.all()
    serializer_class = PlannedBudgetSerializer

    def list(self, request, *args, **kwargs):
        dateFrom = request.GET.get(
            "dateFrom", datetime.date.today() - datetime.timedelta(days=30)
        )
        dateTo = request.GET.get("dateTo", datetime.date.today())

        queryset = (
            self.get_queryset()
            .select_related("category")
            .filter(budget_date__lte=dateTo, budget_date__gte=dateFrom)
        )

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
