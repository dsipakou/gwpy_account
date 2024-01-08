from budget import views
from django.urls import path

urlpatterns = [
    path("", views.BudgetList.as_view(), name="budget_list"),
    path("<uuid:uuid>/", views.BudgetDetails.as_view(), name="budget_details"),
    path("usage/", views.MonthlyUsageBudgetList.as_view(), name="usage_budget_list"),
    path(
        "weekly-usage/",
        views.WeeklyUsageList.as_view(),
        name="weekly_usage_budget_list",
    ),
    path("duplicate/", views.DuplicateBudgetView.as_view(), name="duplicate_budget"),
    path("pending/", views.BudgetPendingList.as_view(), name="pending_budget"),
]
