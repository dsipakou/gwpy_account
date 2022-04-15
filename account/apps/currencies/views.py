from currencies.models import Currency
from currencies.serializers import CurrencySerializer
from rest_framework.exceptions import ValidationError
from rest_framework.generics import ListCreateAPIView, RetrieveUpdateDestroyAPIView


class CurrencyList(ListCreateAPIView):
    queryset = Currency.objects.all()
    serializer_class = CurrencySerializer


class CurrencyDetails(RetrieveUpdateDestroyAPIView):
    queryset = Currency.objects.all()
    serializer_class = CurrencySerializer
    lookup_field = "uuid"

    def perform_destroy(self, instance):
        if instance.is_base:
            raise ValidationError("Base currency cannot be deleted.")

        if instance.is_default:
            raise ValidationError("Default currency cannot be deleted.")

        return super().perform_destroy(instance)
