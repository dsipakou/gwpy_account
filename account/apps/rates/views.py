import datetime

from currencies.models import Currency
from rates.models import Rate
from rates.serializers import (RateChartDataSerializer, RateChartSerializer,
                               RateSerializer)
from rates.utils import generate_date_seq
from rest_framework.generics import (ListAPIView, ListCreateAPIView,
                                     RetrieveUpdateDestroyAPIView)
from rest_framework.response import Response


class RateList(ListCreateAPIView):
    queryset = Rate.objects.order_by("rate_date").reverse()[:180]
    serializer_class = RateSerializer


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
