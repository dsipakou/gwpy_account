from django.urls import path
from rates import views

urlpatterns = [
    path("", views.RateList.as_view(), name="rate_list"),
    path("<uuid:uuid>/", views.RateDetails.as_view(), name="rate_details"),
    path("chart/", views.RateChartData.as_view(), name="rate_chart_data"),
]
