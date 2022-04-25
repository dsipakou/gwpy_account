from rest_framework import status
from rest_framework.generics import (ListCreateAPIView,
                                     RetrieveUpdateDestroyAPIView)
from rest_framework.response import Response
from transactions.models import Transaction
from transactions.serializers import (TransactionCreateSerializer,
                                      TransactionSerializer)
from transactions.services import TransactionService


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
    serializer_class = TransactionSerializer
    lookup_field = "uuid"
