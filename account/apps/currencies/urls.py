from django.urls import path

from currencies import views

urlpatterns = [
    path("", views.CurrencyList.as_view(), name="currency_list"),
    path("<uuid:uuid>/", views.CurrencyDetails.as_view(), name="currency_details"),
]
