from django.urls import path
from users import views

urlpatterns = [
    path("", views.UserList.as_view(), name="user_list"),
    path("login/", views.UserAuth.as_view(), name="user_auth"),
    path("currency/", views.CurrencyView.as_view(), name="default_currency"),
    path("register/", views.RegisterView.as_view(), name="register"),
    path("invite/", views.InviteView.as_view(), name="invite"),
    path("invite/<uuid:uuid>", views.RevokeInviteView.as_view(), name="invite_revoke"),
]
