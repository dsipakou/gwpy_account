from django.urls import path
from users import views

urlpatterns = [
    path("", views.UserList.as_view(), name="user_list"),
    path("login/", views.UserAuth.as_view(), name="user_auth"),
    path("currency/", views.CurrencyView.as_view(), name="default_currency"),
]
