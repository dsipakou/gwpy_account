import datetime

from budget import serializers
from budget.models import Budget
from budget.serializers import DuplicateResponseSerializer
from budget.services import BudgetService
from rest_framework import status
from rest_framework.authentication import TokenAuthentication
from rest_framework.exceptions import ValidationError
from rest_framework.generics import (GenericAPIView, ListAPIView,
                                     ListCreateAPIView,
                                     RetrieveUpdateDestroyAPIView)
from rest_framework.response import Response


class BudgetList(ListCreateAPIView):
    queryset = Budget.objects.select_related("category").all()
    serializer_class = serializers.BudgetSerializer

    def create(self, request, *args, **kwargs):
        """Check if category is parent category

        Raises:
            ValidationError: when category is not parent category
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if serializer.validated_data["category"].parent is not None:
            raise ValidationError("Only parent categories can be used for budgets.")
        instance = serializer.save()
        headers = self.get_success_headers(serializer.data)

        BudgetService.create_budget_multicurrency_amount([instance.uuid])

        return Response(
            serializer.data, status=status.HTTP_201_CREATED, headers=headers
        )


class BudgetDetails(RetrieveUpdateDestroyAPIView):
    queryset = Budget.objects.all()
    serializer_class = serializers.BudgetSerializer
    lookup_field = "uuid"

    def perform_update(self, serializer):
        """Check if category is parent category

        Raises:
            ValidationError: when category is not parent category
        """

        if serializer.validated_data["category"].parent is not None:
            raise ValidationError("Only parent categories can be used for budgets.")
        instance = serializer.save()
        BudgetService.create_budget_multicurrency_amount([instance.uuid])


class PlannedBudgetList(ListAPIView):
    authentication_classes = (TokenAuthentication,)
    queryset = Budget.objects.all()
    serializer_class = serializers.PlannedBudgetSerializer

    def list(self, request, *args, **kwargs):
        dateFrom = request.GET.get(
            "dateFrom", datetime.date.today() - datetime.timedelta(days=30)
        )
        dateTo = request.GET.get("dateTo", datetime.date.today())

        queryset = (
            self.get_queryset()
            .select_related("user")
            .select_related("category")
            .select_related("currency")
            .filter(budget_date__lte=dateTo, budget_date__gte=dateFrom)
        )

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


class ActualUsageBudgetList(ListAPIView):
    serializer_class = serializers.CategoryBudgetSerializer

    def list(self, request, *args, **kwargs):
        date_from = request.GET.get(
            "dateFrom", datetime.date.today() - datetime.timedelta(days=30)
        )
        date_to = request.GET.get("dateTo", datetime.date.today())
        user = request.GET.get("user")

        categories = BudgetService.load_budget(date_from, date_to, user)

        serializer = self.get_serializer(categories, many=True)
        return Response(serializer.data)


class WeeklyUsageList(ListAPIView):
    serializer_class = serializers.BudgetUsageSerializer

    def list(self, request, *args, **kwargs):
        start = datetime.datetime.now()
        date_from = request.GET.get(
            "dateFrom", datetime.date.today() - datetime.timedelta(days=30)
        )
        date_to = request.GET.get("dateTo", datetime.date.today())
        user = request.GET.get("user")

        budgets = BudgetService.load_weekly_budget(date_from, date_to, user)

        serializer = self.get_serializer(budgets, many=True)
        return Response(serializer.data)


class ArchiveView(ListAPIView):
    serializer_class = serializers.ArchiveSerializer

    def list(self, request, *args, **kwargs):
        current_date = request.GET.get("date")
        category_uuid = request.GET.get("category")

        archive = BudgetService.get_archive(current_date, category_uuid)

        serializer = self.get_serializer(archive, many=True)
        return Response(serializer.data)


class DuplicateBudgetView(GenericAPIView):
    serializer_class = serializers.DuplicateRequestSerializer

    def get(self, request, *args, **kwargs):
        if (recurrent_type := request.query_params.get("type")) is not None:
            budgets = BudgetService.get_duplicate_budget_candidates(recurrent_type)
            response_serializer = DuplicateResponseSerializer(data=budgets, many=True)
            response_serializer.is_valid(raise_exception=True)
            return Response(response_serializer.data)
        else:
            return Response(status=status.HTTP_200_OK, data=[])

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        BudgetService.duplicate_budget(serializer.data["uuids"])
        return Response(status=status.HTTP_201_CREATED)
