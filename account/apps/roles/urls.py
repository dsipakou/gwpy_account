from roles import views
from django.urls import path

urlpatterns = [
    path("", views.RolesList.as_view(), name="roles_list"),
]
