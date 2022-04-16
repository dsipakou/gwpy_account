from django.urls import path
from transactions import views

urlpatterns = [
    path("", views.TransactionList.as_view(), name="transaction_list"),
    path(
        "<uuid:uuid>/", views.TransactionDetails.as_view(), name="transaction_details"
    ),
]
