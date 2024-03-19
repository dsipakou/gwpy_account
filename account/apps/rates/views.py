from currencies.models import Currency
from django.db.models import F, Window
from django.db.models.functions import RowNumber
from rates.filters import DateFilter
from rates.models import Rate
from rates.serializers import (
    AvailableRates,
    CreateBatchedRateSerializer,
    RateChartDataSerializer,
    RateChartSerializer,
    RateSerializer,
)
from rates.services import RateService
from rates.utils import generate_date_seq
from rest_framework.generics import (
    CreateAPIView,
    GenericAPIView,
    ListAPIView,
    ListCreateAPIView,
    RetrieveUpdateDestroyAPIView,
)
from rest_framework.response import Response
from rest_framework.status import HTTP_400_BAD_REQUEST
from users.filters import FilterByUser
from workspaces.filters import FilterByWorkspace


class RateList(ListCreateAPIView):
    queryset = Rate.objects.all()
    pagination_class = None
    filter_backends = (FilterByWorkspace,)

    serializer_class = RateSerializer

    def get_queryset(self):
        qs = self.filter_queryset(self.queryset)
        limit = int(self.request.GET.get("limit", 60))
        grouped_queryset = qs.annotate(
            seq_number=Window(
                expression=RowNumber(),
                partition_by=F("currency"),
                order_by=F("rate_date").desc(),
            )
        )
        queryset = grouped_queryset.filter(seq_number__lte=limit)
        # TODO: Remove this if OK
        # sql, params = grouped_queryset.query.sql_with_params()
        # breakpoint()
        # queryset = Rate.objects.raw(
        #     """
        #     SELECT *
        #     FROM ({}) as seq_table
        #     WHERE seq_table.seq_number <= %s
        # """.format(
        #         sql
        #     ),
        #     [*params, limit],
        # )
        return queryset


class CreateBatchedRate(CreateAPIView):
    serializer_class = CreateBatchedRateSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        RateService.create_batched_rates(serializer.data)
        return Response(serializer.data)


class RateDayData(ListAPIView):
    queryset = Rate.objects.all()
    filter_backends = (DateFilter, FilterByWorkspace)
    serializer_class = RateSerializer


class RateDetails(RetrieveUpdateDestroyAPIView):
    queryset = Rate.objects.all()
    filter_backends = (FilterByWorkspace,)
    serializer_class = RateSerializer
    lookup_field = "uuid"


class RateChartData(ListAPIView):
    queryset = Currency.objects.all()
    filter_backends = (FilterByWorkspace,)
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
        currency_uuids = (
            self.filter_queryset(self.get_queryset())
            .filter(is_base=False)
            .values_list("uuid", flat=True)
        )
        requested_dates = generate_date_seq(range)
        rates = []
        for uuid in currency_uuids:
            rate_values = (
                self.filter_queryset(Rate.objects.all())
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
    queryset = Rate.objects.all()
    filter_backends = (FilterByWorkspace,)

    def get(self, request, *args, **kwargs):
        date = request.GET.get("date")
        if not date:
            return Response(
                status=HTTP_400_BAD_REQUEST,
                exception=True,
                data={"details": "date_not_found"},
            )
        currencies = self.filter_queryset(Currency.objects.all())
        rates_qs = (
            self.filter_queryset(self.get_queryset())
            .filter(rate_date=date)
            .values("currency_id", "rate")
        )
        rates = {rate["currency_id"]: rate["rate"] for rate in rates_qs}
        first_rate = Rate.objects.filter(rate_date=date).first()
        available_rates = {}
        for currency in currencies:
            # if rate exists for current item
            # or
            # if currency is base for the first rate on date
            # or
            # if no rates but currency is base now
            if currency.uuid in rates:
                available_rates[currency.code] = rates[currency.uuid]
            elif (first_rate and currency == first_rate.base_currency) or (
                not first_rate and currency.is_base
            ):
                available_rates[currency.code] = 1
            else:
                available_rates[currency.code] = None
        serializer_data = AvailableRates(data=available_rates)
        return Response(serializer_data.data)
