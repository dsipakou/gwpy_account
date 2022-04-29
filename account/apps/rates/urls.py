from django.urls import path, register_converter
from rates import converters, views

register_converter(converters.YearMonthDayConverter, "ymddate")

urlpatterns = [
    path("", views.RateList.as_view(), name="rate_list"),
    path("<uuid:uuid>/", views.RateDetails.as_view(), name="rate_details"),
    path("chart/", views.RateChartData.as_view(), name="rate_chart_data"),
    path("day/<ymddate:rate_date>/", views.RateDayData.as_view(), name="rate_day_data"),
]
