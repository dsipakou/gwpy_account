from rest_framework.generics import ListCreateAPIView, RetrieveUpdateDestroyAPIView
from transactions.models import Transaction
from transactions.serializers import TransactionSerializer


class TransactionList(ListCreateAPIView):
    queryset = Transaction.objects.all()
    serializer_class = TransactionSerializer


class TransactionDetails(RetrieveUpdateDestroyAPIView):
    queryset = Transaction.objects.all()
    serializer_class = TransactionSerializer
    lookup_field = "uuid"
