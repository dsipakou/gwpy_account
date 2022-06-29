import datetime

from budget.models import Budget
from budget.serializers import (ArchiveSerializer, BudgetSerializer,
                                BudgetUsageSerializer,
                                CategoryBudgetSerializer,
                                PlannedBudgetSerializer)
from budget.services import BudgetService
from html5lib import serialize
from rest_framework.exceptions import ValidationError
from rest_framework.generics import (ListAPIView, ListCreateAPIView,
                                     RetrieveUpdateDestroyAPIView)
from rest_framework.response import Response


class BudgetList(ListCreateAPIView):
    queryset = Budget.objects.select_related("category").all()
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


class ActualUsageBudgetList(ListAPIView):
    serializer_class = CategoryBudgetSerializer

    def list(self, request, *args, **kwargs):
        date_from = request.GET.get(
            "dateFrom", datetime.date.today() - datetime.timedelta(days=30)
        )
        date_to = request.GET.get("dateTo", datetime.date.today())

        start = datetime.datetime.now()
        categories = BudgetService.load_budget(date_from, date_to)

        serializer = self.get_serializer(categories, many=True)
        return Response(serializer.data)


class WeeklyUsageList(ListAPIView):
    serializer_class = BudgetUsageSerializer

    def list(self, request, *args, **kwargs):
        start = datetime.datetime.now()
        date_from = request.GET.get(
            "dateFrom", datetime.date.today() - datetime.timedelta(days=30)
        )
        date_to = request.GET.get("dateTo", datetime.date.today())

        budgets = BudgetService.load_weekly_budget(date_from, date_to)

        serializer = self.get_serializer(budgets, many=True)
        return Response(serializer.data)


class ArchiveView(ListAPIView):
    serializer_class = ArchiveSerializer

    def list(self, request, *args, **kwargs):
        current_date = request.GET.get("date")

        archive = BudgetService.get_archive(current_date)

        serializer = self.get_serializer(archive, many=True)
        return Response(serializer.data)
