from currencies import views
from django.urls import path

urlpatterns = [
    path("", views.CurrencyList.as_view(), name="currency_list"),
    path("<uuid:uuid>/", views.CurrencyDetails.as_view(), name="currency_details"),
]
