from rest_framework.exceptions import ValidationError
from rest_framework.generics import ListCreateAPIView, RetrieveUpdateDestroyAPIView

from currencies.models import Currency
from currencies.serializers import CurrencySerializer
from rates.models import Rate
from workspaces.filters import FilterByWorkspace


class CurrencyList(ListCreateAPIView):
    queryset = Currency.objects.all().order_by("created_at")
    filter_backends = (FilterByWorkspace,)
    serializer_class = CurrencySerializer


class CurrencyDetails(RetrieveUpdateDestroyAPIView):
    queryset = Currency.objects.all()
    filter_backends = (FilterByWorkspace,)
    serializer_class = CurrencySerializer
    lookup_field = "uuid"

    def perform_destroy(self, instance):
        if instance.is_base:
            raise ValidationError("Base currency cannot be deleted.")

        if instance.is_default:
            raise ValidationError("Default currency cannot be deleted.")

        if Rate.objects.filter(currency=instance).exists():
            raise ValidationError(
                "Currency cannot be deleted because at least one rate exists."
            )

        return super().perform_destroy(instance)
