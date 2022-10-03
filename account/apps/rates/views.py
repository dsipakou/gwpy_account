from currencies.models import Currency
from rates.filters import DateFilter
from rates.models import Rate
from rates.serializers import (AvailableRates, CreateBatchedRateSerializer,
                               RateChartDataSerializer, RateChartSerializer,
                               RateSerializer)
from rates.services import RateService
from rates.utils import generate_date_seq
from rest_framework.generics import (CreateAPIView, GenericAPIView,
                                     ListAPIView, ListCreateAPIView,
                                     RetrieveUpdateDestroyAPIView)
from rest_framework.response import Response


class RateList(ListCreateAPIView):
    queryset = Rate.objects.order_by("rate_date").reverse()[:180]
    serializer_class = RateSerializer


class CreateBatchedRate(CreateAPIView):
    serializer_class = CreateBatchedRateSerializer

    def create(self, request, *args, **kwards):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        RateService.create_batched_rates(serializer.data)
        return Response(serializer.data)


class RateDayData(ListAPIView):
    queryset = Rate.objects.all()
    serializer_class = RateSerializer
    filter_backends = (DateFilter,)


class RateDetails(RetrieveUpdateDestroyAPIView):
    queryset = Rate.objects.all()
    serializer_class = RateSerializer
    lookup_field = "uuid"


class RateChartData(ListAPIView):
    queryset = Rate.objects.all()
    serializer_class = RateChartSerializer

    def list(self, request, *args, **kwargs):
        """Get data for currency charts with various ranges

        Args:
            request (range): Requested range in days

        Returns: array of objects
            [
                {
                    "currencyUuid": "<uuid>",
                    "data": [
                        { "rateDate": "<date>", "rate": "<rate>" },
                        ...
                    ]
                },
                ...
            ]
        """

        range = int(request.GET.get("range", 30))
        currency_uuids = Currency.objects.filter(is_base=False).values_list(
            "uuid", flat=True
        )
        requested_dates = generate_date_seq(range)
        rates = []
        for uuid in currency_uuids:
            rate_values = (
                self.get_queryset()
                .filter(currency__uuid=uuid, rate_date__in=requested_dates)
                .values("rate_date", "rate")
            )

            chart_data_flat = {date: None for date in requested_dates}
            for value in rate_values:
                chart_data_flat[value["rate_date"]] = value["rate"]

            chart_data = [
                {"rate_date": date, "rate": rate}
                for date, rate in chart_data_flat.items()
            ]

            serialized_data = RateChartDataSerializer(data=chart_data, many=True)
            serialized_data.is_valid()

            rates.append(
                {
                    "currency_uuid": uuid,
                    "data": serialized_data.data,
                }
            )
        serializer = self.get_serializer(rates, many=True)
        return Response(serializer.data)


class AvailableRates(GenericAPIView):
    def get(self, request, rate_date, *args, **kwargs):
        currencies = Currency.objects.all()
        rates = Rate.objects.filter(rate_date=rate_date).values_list(
            "currency_id", flat=True
        )
        first_rate = Rate.objects.filter(rate_date=rate_date).first()
        available_rates = {}
        for currency in currencies:
            # if rate exists for current item
            # or
            # if currency is base for the first rate
            # or
            # if no rates but currency is base now
            if (
                currency.uuid in rates
                or (first_rate and currency == first_rate.base_currency)
                or (not first_rate and currency.is_base)
            ):
                available_rates[currency.code] = True
            else:
                available_rates[currency.code] = False
        serializer_data = AvailableRates(data=available_rates)
        return Response(serializer_data.data)
