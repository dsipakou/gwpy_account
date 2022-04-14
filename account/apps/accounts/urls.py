from accounts import views
from django.urls import path

urlpatterns = [
    path("", views.AccountList.as_view(), name="account_list"),
    path("<uuid:uuid>/", views.AccountDetails.as_view(), name="account_details"),
]
