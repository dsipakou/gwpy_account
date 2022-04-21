import datetime

from budget.models import Budget
from budget.serializers import (ActualUsageBudgetSerializer, BudgetSerializer,
                                PlannedBudgetSerializer)
from django.db.models import Case, F, OuterRef, Value, When
from django.forms import CharField
from rates.models import Rate
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
    serializer_class = ActualUsageBudgetSerializer

    def list(self, request, *args, **kwargs):
        dateFrom = request.GET.get(
            "dateFrom", datetime.date.today() - datetime.timedelta(days=30)
        )
        dateTo = request.GET.get("dateTo", datetime.date.today())

        curr = datetime.datetime.now()
        transactions = (
            self.get_queryset()
            .filter(budget__budget_date__lte=dateTo, budget__budget_date__gte=dateFrom)
            .select_related("budget", "currency")
        )

        print(datetime.datetime.now() - curr)

        serializer = self.get_serializer(transactions, many=True)
        print(datetime.datetime.now() - curr)
        return Response(serializer.data)
