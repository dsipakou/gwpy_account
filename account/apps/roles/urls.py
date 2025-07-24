from django.urls import path
from roles import views

urlpatterns = [
    path("", views.RolesList.as_view(), name="roles_list"),
]
