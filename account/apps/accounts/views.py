from accounts.models import Account
from accounts.serializers import AccountSerializer
from rest_framework.authentication import TokenAuthentication
from rest_framework.generics import (ListCreateAPIView,
                                     RetrieveUpdateDestroyAPIView)

from account.apps.users.filters import FilterByUser


class AccountList(ListCreateAPIView):
    queryset = Account.objects.all()
    # filter_backends = (FilterByUser, )
    serializer_class = AccountSerializer


class AccountDetails(RetrieveUpdateDestroyAPIView):
    queryset = Account.objects.all()
    # filter_backends = (FilterByUser, )
    serializer_class = AccountSerializer
    lookup_field = "uuid"
