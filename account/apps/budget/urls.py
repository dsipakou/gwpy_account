from budget import views
from django.urls import path

urlpatterns = [
    path("", views.BudgetList.as_view(), name="budget_list"),
    path("<uuid:uuid>/", views.BudgetDetails.as_view(), name="budget_details"),
]