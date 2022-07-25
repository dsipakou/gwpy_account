from datetime import date, datetime, timedelta

from rest_framework import status
from rest_framework.generics import (ListAPIView, ListCreateAPIView,
                                     RetrieveUpdateDestroyAPIView)
from rest_framework.response import Response
from transactions.models import Transaction
from transactions.serializers import (GroupedTransactionSerializer,
                                      ReportByMonthSerializer,
                                      TransactionCreateSerializer,
                                      TransactionDetailsSerializer,
                                      TransactionSerializer)
from transactions.services import ReportService, TransactionService


class TransactionList(ListCreateAPIView):
    serializer_class = TransactionSerializer

    def list(self, request, *args, **kwargs):
        transactions = TransactionService.load_transactions()

        serializer = self.get_serializer(transactions, many=True)
        return Response(serializer.data)

    def create(self, request, *args, **kwargs):
        serializer = TransactionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()
        headers = self.get_success_headers(serializer.data)

        transaction = TransactionService.load_transaction(instance.uuid)
        serializer = self.get_serializer(transaction)
        return Response(
            serializer.data, status=status.HTTP_201_CREATED, headers=headers
        )


class TransactionDetails(RetrieveUpdateDestroyAPIView):
    queryset = Transaction.objects.all()
    serializer_class = TransactionDetailsSerializer
    lookup_field = "uuid"

    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)


class TransactionGroupedList(ListAPIView):
    serializer_class = GroupedTransactionSerializer

    def list(self, request, *args, **kwargs):
        date_from = request.GET.get("dateFrom", date.today() - timedelta(days=30))
        date_to = request.GET.get("dateTo", date.today())
        transactions = TransactionService.load_grouped_transactions(
            date_from=date_from, date_to=date_to
        )

        serializer = self.get_serializer(transactions, many=True)
        return Response(serializer.data)


class TransactionReportList(ListAPIView):
    serializer_class = ReportByMonthSerializer

    def list(self, request, *args, **kwargs):
        date_to = datetime.strptime(request.GET["dateTo"], "%Y-%m")
        date_from = datetime.strptime(request.GET["dateFrom"], "%Y-%m")
        currency_code = request.GET.get("currency")
        response = ReportService.get_year_report(date_from, date_to, currency_code)
        serializer = self.get_serializer(response, many=True)
        return Response(serializer.data)
