from rest_framework.filters import BaseFilterBackend


class DateFilter(BaseFilterBackend):
    def filter_queryset(self, request, queryset, view):
        filter_date = view.kwargs.get("rate_date")
        if filter_date:
            queryset = queryset.filter(rate_date=filter_date)
        return queryset
