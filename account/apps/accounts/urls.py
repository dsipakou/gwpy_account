from django.urls import path
from accounts import views

urlpatterns = [
    path('', views.AccountList.as_view(), name='account_list'),
]
