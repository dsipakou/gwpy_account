from django.shortcuts import render
from budget.serializers import BudgetSerializer
from budget.models import Budget
from rest_framework.generics import ListCreateAPIView, RetrieveUpdateDestroyAPIView


class BudgetList(ListCreateAPIView):
    queryset = Budget.objects.all()
    serializer_class = BudgetSerializer


class BudgetDetails(RetrieveUpdateDestroyAPIView):
    queryset = Budget.objects.all()
    serializer_class = BudgetSerializer
    lookup_field = "uuid"