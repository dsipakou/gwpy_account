from django.urls import path

from categories import views

urlpatterns = [
    path("", views.CategoryList.as_view(), name="category_list"),
    path("<uuid:uuid>/", views.CategoryDetails.as_view(), name="category_details"),
    path(
        "<uuid:uuid>/reassign/",
        views.CategoryReassignView.as_view(),
        name="category_reassign",
    ),
]
