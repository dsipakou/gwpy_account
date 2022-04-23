from rest_framework.generics import (ListCreateAPIView,
                                     RetrieveUpdateDestroyAPIView)
from rest_framework.response import Response
from transactions.models import Transaction
from transactions.serializers import TransactionSerializer
from transactions.services import TransactionService


class TransactionList(ListCreateAPIView):
    queryset = (
        Transaction.objects.all()
        .select_related("category")
        .order_by("-created_at")[:15]
    )
    serializer_class = TransactionSerializer


class TransactionDetails(RetrieveUpdateDestroyAPIView):
    queryset = Transaction.objects.all()
    serializer_class = TransactionSerializer
    lookup_field = "uuid"

    def list(self, request, *args, **kwargs):
        transactions = TransactionService.load_transactions()

        serializer = self.get_serializer(transactions, many=True)
        serializer.data
        return Response(serializer.data)
