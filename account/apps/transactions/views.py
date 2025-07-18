import functools
from datetime import date, datetime, timedelta

from categories import constants
from categories.models import Category
from django.db import transaction
from django.db.models.query import QuerySet
from django.utils.timezone import now
from rest_framework import status
from rest_framework.generics import (
    CreateAPIView,
    ListAPIView,
    ListCreateAPIView,
    RetrieveDestroyAPIView,
    UpdateAPIView,
)
from rest_framework.response import Response
from users.filters import FilterByUser
from workspaces.filters import FilterByWorkspace

from account.apps.transactions.serializers import LastViewedSerializer
from transactions.models import LastViewed, Transaction
from transactions.serializers import (
    AccountUsageSerializer,
    GroupedTransactionSerializer,
    IncomeSerializer,
    ReportByMonthSerializer,
    ReportChartSerializer,
    TransactionBulkCreateSerializer,
    TransactionBulkSerializer,
    TransactionBulkUpdateSerializer,
    TransactionCreateSerializer,
    TransactionDetailsSerializer,
    TransactionSerializer,
    TransactionUpdateSerializer,
)
from transactions.services import ReportService, TransactionService


class TransactionList(ListCreateAPIView, UpdateAPIView):
    queryset = Transaction.objects.all()
    serializer_class = TransactionSerializer
    filter_backends = (FilterByUser, FilterByWorkspace)

    def list(self, request, *args, **kwargs):
        data = {}

        if limit := request.GET.get("limit"):
            try:
                data["limit"] = int(limit)
            except:
                pass

        queryset = self.filter_queryset(self.get_queryset())

        if date_from := request.GET.get("dateFrom"):
            data["date_from"] = date_from

        if date_to := request.GET.get("dateTo"):
            data["date_to"] = date_to

        if transaction_type := request.GET.get("type"):
            if transaction_type == "outcome":
                data["category_type"] = constants.EXPENSE
            else:
                data["category_type"] = constants.INCOME

        data["order_by"] = "transaction_date"

        transactions = TransactionService.load_transactions(queryset, **data)

        serializer = self.get_serializer(transactions, many=True)
        return Response(serializer.data)

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = TransactionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()
        headers = self.get_success_headers(serializer.data)
        workspace = request.user.active_workspace

        TransactionService.create_transaction_multicurrency_amount(
            [instance.uuid], workspace=workspace
        )
        transaction = TransactionService.load_transaction(instance.uuid)
        serializer = TransactionSerializer(transaction)
        return Response(
            serializer.data, status=status.HTTP_201_CREATED, headers=headers
        )

    def get_existing_object(self):
        return Transaction.objects.get(
            uuid=self.request.data["uuid"], workspace=self.request.user.active_workspace
        )

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        instance = self.get_existing_object()
        serializer = TransactionUpdateSerializer(
            instance, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        workspace = request.user.active_workspace
        self.perform_update(serializer)
        TransactionService.create_transaction_multicurrency_amount(
            [instance.uuid], workspace=workspace
        )
        transaction = TransactionService.load_transaction(instance.uuid)
        serializer = TransactionSerializer(transaction)

        return Response(serializer.data, status=status.HTTP_200_OK)


class BudgetTransactions(ListAPIView):
    filter_backends = (FilterByUser, FilterByWorkspace)
    serializer_class = TransactionSerializer

    def get_queryset(self) -> QuerySet:
        return (
            Transaction.objects.filter(budget__uuid=self.kwargs["uuid"])
            .select_related(
                "account",
                "budget",
                "category",
                "category__parent",
                "currency",
                "multicurrency",
                "user",
            )
            .order_by("transaction_date")
        )

    def list(self, request, *args, **kwargs):
        transactions = TransactionService.proceed_transactions(
            self.filter_queryset(self.get_queryset())
        )
        serializer = self.get_serializer(transactions, many=True)
        return Response(serializer.data)


class AccountUsage(ListAPIView):
    filter_backends = (FilterByUser, FilterByWorkspace)
    serializer_class = AccountUsageSerializer

    def get_queryset(self) -> QuerySet:
        start_of_month = now().replace(day=1)

        return (
            Transaction.objects.filter(
                account__uuid=self.kwargs["uuid"],
                transaction_date__gte=start_of_month,
            )
            .select_related(
                "account",
                "budget",
                "category",
                "category__parent",
                "currency",
                "multicurrency",
                "user",
            )
            .order_by("-transaction_date")
        )

    def list(self, request, *args, **kwargs):
        spent_transactions = TransactionService.proceed_transactions(
            self.filter_queryset(
                self.get_queryset().filter(category__type=constants.EXPENSE)
            )
        )
        income_transactions = TransactionService.proceed_transactions(
            self.filter_queryset(
                self.get_queryset().filter(category__type=constants.INCOME)
            )
        )
        default_currency = request.user.default_currency
        spent_sum = functools.reduce(
            lambda x, y: x + y,
            [
                t["spent_in_currencies"].get(default_currency.code, 0)
                for t in spent_transactions
            ],
            0,
        )
        income_sum = functools.reduce(
            lambda x, y: x + y,
            [
                t["spent_in_currencies"].get(default_currency.code, 0)
                for t in income_transactions
            ],
            0,
        )
        serializer = AccountUsageSerializer(
            {
                "spent": round(spent_sum, 2),
                "income": round(income_sum, 2),
            }
        )
        return Response(serializer.data)


class CategoryTransactions(ListAPIView):
    filter_backends = (FilterByUser, FilterByWorkspace)
    serializer_class = TransactionSerializer

    def get_queryset(self) -> QuerySet:
        return (
            Transaction.objects.filter(category__uuid=self.kwargs["uuid"])
            .select_related(
                "account",
                "budget",
                "category",
                "category__parent",
                "currency",
                "multicurrency",
                "user",
            )
            .order_by("-transaction_date")
        )

    def list(self, request, *args, **kwargs):
        transactions = TransactionService.proceed_transactions(
            self.filter_queryset(self.get_queryset())
        )
        serializer = self.get_serializer(transactions[:20], many=True)
        return Response(serializer.data)


class TransactionDetails(RetrieveDestroyAPIView):
    queryset = Transaction.objects.all()
    serializer_class = TransactionDetailsSerializer
    filter_backends = (FilterByUser, FilterByWorkspace)
    lookup_field = "uuid"


class TransactionGroupedList(ListAPIView):
    filter_backends = (FilterByUser, FilterByWorkspace)
    serializer_class = GroupedTransactionSerializer

    def list(self, request, *args, **kwargs):
        qs = self.filter_queryset(self.get_queryset())
        date_from = request.GET.get("dateFrom", date.today() - timedelta(days=30))
        date_to = request.GET.get("dateTo", date.today())
        transactions = TransactionService.load_grouped_transactions(
            qs, date_from=date_from, date_to=date_to
        )

        serializer = self.get_serializer(transactions, many=True)
        return Response(serializer.data)


class TransactionReportList(ListAPIView):
    filter_backends = (FilterByUser, FilterByWorkspace)
    serializer_class = ReportByMonthSerializer

    def list(self, request, *args, **kwargs):
        date_to = datetime.strptime(request.GET["dateTo"], "%Y-%m-%d")
        date_from = datetime.strptime(request.GET["dateFrom"], "%Y-%m-%d")
        currency_code = request.GET.get("currency")
        response = ReportService.get_year_report(
            date_from, date_to, currency_code, request.user.active_workspace.uuid
        )
        serializer = self.get_serializer(response, many=True)
        return Response(serializer.data)


class TransactionReportMonthly(ListAPIView):
    queryset = Transaction.objects.all()
    filter_backends = (FilterByWorkspace,)
    serializer_class = ReportChartSerializer

    def list(self, request, *args, **kwargs):
        qs = self.filter_queryset(self.get_queryset())
        categories_qs = self.filter_queryset(Category.objects.all())
        date_to = datetime.strptime(request.GET["dateTo"], "%Y-%m-%d")
        date_from = datetime.strptime(request.GET["dateFrom"], "%Y-%m-%d")
        currency_code = request.GET.get("currency")
        number_of_days = request.GET.get("numberOfDays")
        data = ReportService.get_chart_report(
            qs, categories_qs, date_from, date_to, currency_code, number_of_days
        )
        serializer = self.get_serializer(data, many=True)
        return Response(serializer.data)


class TransactionIncomeList(ListAPIView):
    filter_backends = (FilterByUser, FilterByWorkspace)
    serializer_class = IncomeSerializer

    def list(self, request, *args, **kwargs):
        date_to = datetime.strptime(request.GET["dateTo"], "%Y-%m")
        date_from = datetime.strptime(request.GET["dateFrom"], "%Y-%m")
        transactions = Transaction.objects.filter(
            category__type=constants.INCOME,
            transaction_date__gte=date_from,
            transaction_date__lte=date_to,
        ).select_related("multicurrency")
        data = TransactionService.group_by_month(transactions)
        serializer = self.get_serializer(instance=transactions, many=True)
        return Response(serializer.data)


class TransactionsLastAddedView(ListCreateAPIView):
    filter_backends = (FilterByUser, FilterByWorkspace)
    serializer_class = TransactionSerializer

    def get_queryset(self) -> QuerySet:
        user = self.request.user
        try:
            last_viewed = LastViewed.objects.get(user=user)
        except LastViewed.DoesNotExist:
            last_viewed = None
        qs = (
            Transaction.objects.select_related(
                "account",
                "budget",
                "category",
                "category__parent",
                "currency",
                "multicurrency",
                "user",
            )
            .exclude(user=user)
            .order_by("-pk")
        )

        if last_viewed:
            qs = qs.filter(created_at__gt=last_viewed.transaction.created_at)

        return qs

    def list(self, request, *args, **kwargs):
        transactions = TransactionService.proceed_transactions(
            self.filter_queryset(self.get_queryset())
        )
        serializer = self.get_serializer(transactions, many=True)
        return Response(serializer.data)

    def create(self, request, *args, **kwargs):
        user = request.data["user"]
        LastViewed.objects.filter(user=user).delete()
        serializer = LastViewedSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(status=status.HTTP_201_CREATED)


class TransactionBulkCreate(CreateAPIView):
    filter_backends = (FilterByUser, FilterByWorkspace)
    serializer_class = TransactionBulkCreateSerializer

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, many=True)
        serializer.is_valid(raise_exception=True)
        instances = serializer.save()

        headers = self.get_success_headers(serializer.data)
        workspace = request.user.active_workspace

        for instance in instances:
            TransactionService.create_transaction_multicurrency_amount(
                [instance.uuid], workspace=workspace
            )

        transactions = []
        for idx, instance in enumerate(instances):
            transactions.append(
                {
                    "row_id": serializer.validated_data[idx]["row_id"],
                    **TransactionService.load_transaction(instance.uuid),
                }
            )

        response_serializer = TransactionBulkSerializer(transactions, many=True)
        return Response(
            response_serializer.data, status=status.HTTP_201_CREATED, headers=headers
        )


class TransactionBulkUpdate(UpdateAPIView):
    filter_backends = (FilterByUser, FilterByWorkspace)
    serializer_class = TransactionBulkUpdateSerializer

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        instance = self.get_existing_object()
        serializer = self.get_serializer(
            instance, data=request.data, partial=True, many=True
        )
        serializer.is_valid(raise_exception=True)
        workspace = request.user.active_workspace
        instances = self.perform_update(serializer)

        for instance in instances:
            TransactionService.create_transaction_multicurrency_amount(
                [instance.uuid], workspace=workspace
            )

        TransactionService.create_transaction_multicurrency_amount(
            [instance.uuid], workspace=workspace
        )
        transaction = TransactionService.load_transaction(instance.uuid)
        serializer = TransactionSerializer(transaction)

        return Response(serializer.data, status=status.HTTP_200_OK)