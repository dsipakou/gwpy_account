import datetime

from budget.models import Budget
from budget.serializers import (BudgetSerializer, CategoryBudgetSerializer,
                                PlannedBudgetSerializer)
from categories.models import Category
from django.db.models import CharField, Count, OuterRef, Prefetch, Q
from rest_framework.exceptions import ValidationError
from rest_framework.generics import (ListAPIView, ListCreateAPIView,
                                     RetrieveUpdateDestroyAPIView)
from rest_framework.response import Response
from transactions.models import Transaction


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


class ActualUsageBudgetList(ListAPIView):
    queryset = Transaction.objects.all()
    serializer_class = CategoryBudgetSerializer

    def list(self, request, *args, **kwargs):
        dateFrom = request.GET.get(
            "dateFrom", datetime.date.today() - datetime.timedelta(days=30)
        )
        dateTo = request.GET.get("dateTo", datetime.date.today())

        transactions = self.get_queryset().order_by("budget__title")

        budgets = Budget.objects.filter(
            budget_date__lte=dateTo, budget_date__gte=dateFrom
        ).prefetch_related(
            Prefetch(
                "transaction_set", queryset=transactions, to_attr="budget_transactions"
            ),
        )

        categories = (
            Category.objects.filter()
            .prefetch_related(
                Prefetch("budget_set", queryset=budgets, to_attr="category_budgets")
            )
            .annotate(
                budget_count=Count(
                    "budget",
                    filter=Q(
                        budget__budget_date__lte=dateTo,
                        budget__budget_date__gte=dateFrom,
                    ),
                ),
            )
            .filter(budget_count__gt=0)
            .order_by("name")
        )

        serializer = self.get_serializer(categories, many=True)
        return Response(serializer.data)
