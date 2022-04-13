from accounts.models import Account
from accounts.serializers import AccountSerializer
from django.shortcuts import render
from rest_framework.generics import ListCreateAPIView


class AccountList(ListCreateAPIView):
    queryset = Account.objects.all()
    serializer_class = AccountSerializer
