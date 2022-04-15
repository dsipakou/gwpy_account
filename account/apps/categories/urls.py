from categories import views
from django.urls import path

urlpatterns = [
    path("", views.CategoryList.as_view(), name="category_list"),
    path("<uuid:uuid>/", views.CategoryDetails.as_view(), name="category_details"),
]
