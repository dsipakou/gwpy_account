from budget import views
from django.urls import path

urlpatterns = [
    path("", views.BudgetList.as_view(), name="budget_list"),
    path("<uuid:uuid>/", views.BudgetDetails.as_view(), name="budget_details"),
    path("planned/", views.PlannedBudgetList.as_view(), name="planned_budget_list"),
    path("usage/", views.ActualUsageBudgetList.as_view(), name="usage_budget_list"),
    path("weekly-usage/", views.WeeklyUsageList.as_view(), name="weekly_usage_budget_list"),
]
