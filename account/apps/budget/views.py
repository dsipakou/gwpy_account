import datetime

from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.generics import (
    GenericAPIView,
    ListAPIView,
    ListCreateAPIView,
    RetrieveUpdateDestroyAPIView,
)
from rest_framework.response import Response

from budget import serializers
from budget.models import Budget
from budget.serializers import DuplicateResponseSerializer
from budget.services import BudgetService
from categories.models import Category
from currencies.models import Currency
from transactions.models import Transaction
from users.filters import FilterByUser
from users.permissions import BaseUserPermission
from workspaces.filters import FilterByWorkspace


class BudgetList(ListCreateAPIView):
    queryset = Budget.objects.select_related("category").all()
    filter_backends = (FilterByUser, FilterByWorkspace)
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
        workspace = request.user.active_workspace

        BudgetService.create_budget_multicurrency_amount(
            [instance.uuid], workspace=workspace
        )

        return Response(
            serializer.data, status=status.HTTP_201_CREATED, headers=headers
        )


class BudgetPendingList(ListAPIView):
    queryset = Budget.objects.filter(budget_date__isnull=True)
    filter_backends = (FilterByUser, FilterByWorkspace)
    serializer_class = serializers.BudgetSerializer


class BudgetDetails(RetrieveUpdateDestroyAPIView):
    queryset = Budget.objects.prefetch_related("transaction_set")
    serializer_class = serializers.BudgetSerializer
    permission_classes = (BaseUserPermission,)
    lookup_field = "uuid"

    def perform_update(self, serializer):
        """Check if category is parent category

        Raises:
            ValidationError: when category is not parent category
        """

        if serializer.validated_data["category"].parent is not None:
            raise ValidationError("Only parent categories can be used for budgets.")
        instance = serializer.save()
        BudgetService.create_budget_multicurrency_amount(
            [instance.uuid], workspace=instance.workspace
        )


class MonthlyUsageBudgetList(ListAPIView):
    queryset = Budget.objects.all()
    filter_backends = (FilterByUser, FilterByWorkspace)
    serializer_class = serializers.CategoryBudgetV2Serializer

    def list(self, request, *args, **kwargs):
        date_from = request.GET.get("dateFrom", datetime.date.today())
        date_to = request.GET.get("dateTo", datetime.date.today())
        user = request.GET.get("user")
        queryset = self.filter_queryset(self.get_queryset())

        categories = BudgetService.load_budget_v2(
            queryset=queryset,
            categories_qs=Category.objects.all(),
            currencies_qs=Currency.objects.filter(
                workspace=request.user.active_workspace
            ),
            transactions_qs=Transaction.objects.prefetch_related("budget").filter(
                workspace=request.user.active_workspace, budget__in=queryset
            ),
            date_from=date_from,
            date_to=date_to,
            user=user,
        )

        serializer = self.get_serializer(categories, many=True)
        return Response(serializer.data)


class WeeklyUsageList(ListAPIView):
    queryset = Budget.objects.all()
    filter_backends = (FilterByUser, FilterByWorkspace)
    serializer_class = serializers.BudgetUsageSerializer

    def list(self, request, *args, **kwargs):
        date_from = request.GET.get(
            "dateFrom", datetime.date.today() - datetime.timedelta(days=30)
        )
        date_to = request.GET.get("dateTo", datetime.date.today())
        user = request.GET.get("user")

        budgets = BudgetService.load_weekly_budget(
            self.filter_queryset(self.get_queryset()),
            Currency.objects.filter(workspace=request.user.active_workspace),
            date_from,
            date_to,
            request.user.active_workspace,
            user,
        )

        serializer = self.get_serializer(budgets, many=True)
        return Response(serializer.data)


class DuplicateBudgetView(GenericAPIView):
    queryset = Budget.objects.all()
    filter_backends = (FilterByUser, FilterByWorkspace)
    serializer_class = serializers.DuplicateRequestSerializer
    permission_classes = (BaseUserPermission,)

    def get(self, request, *args, **kwargs):
        pivot_date = request.query_params.get("date")
        if (recurrent_type := request.query_params.get("type")) is not None:
            budgets = BudgetService.get_duplicate_budget_candidates(
                self.filter_queryset(self.queryset), recurrent_type, pivot_date
            )
            response_serializer = DuplicateResponseSerializer(data=budgets, many=True)
            response_serializer.is_valid(raise_exception=True)
            return Response(response_serializer.data)
        else:
            return Response(status=status.HTTP_200_OK, data=[])

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        workspace = request.user.active_workspace
        BudgetService.duplicate_budget(serializer.data["uuids"], workspace=workspace)
        return Response(status=status.HTTP_201_CREATED)


class LastMonthsBudgetUsageList(ListAPIView):
    queryset = Budget.objects.all()
    filter_backends = (FilterByUser, FilterByWorkspace)
    serializer_class = serializers.LastMonthsUsageSerializer

    def list(self, request, *args, **kwargs):
        month_request = request.GET.get("month")
        if month_request:
            month = datetime.datetime.strptime(month_request, "%Y-%m-%d").date()
        else:
            month = datetime.date.today()
        user = request.GET.get("user")
        category_uuid = request.GET.get("category")

        if not category_uuid:
            return Response(status=status.HTTP_400_BAD_REQUEST)

        queryset = self.filter_queryset(self.get_queryset())

        grouped_transactions = BudgetService.get_last_months_usage(
            transactions=Transaction.objects.prefetch_related("budget").filter(
                budget__in=queryset
            ),
            month=month,
            user=request.user,
            filter_by_user=user,
            category_uuid=category_uuid,
        )

        serializer = self.get_serializer(instance=grouped_transactions, many=True)

        return Response(serializer.data)
