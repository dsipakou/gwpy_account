from rates.models import Rate
from rates.serializers import RateSerializer
from rest_framework.generics import ListCreateAPIView, RetrieveUpdateDestroyAPIView


class RateList(ListCreateAPIView):
    queryset = Rate.objects.all()
    serializer_class = RateSerializer


class RateDetails(RetrieveUpdateDestroyAPIView):
    queryset = Rate.objects.all()
    serializer_class = RateSerializer
    lookup_field = "uuid"
