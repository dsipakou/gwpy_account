from users.permissions import UserRolePermissions
from django.contrib.auth import authenticate
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.generics import (
    CreateAPIView,
    DestroyAPIView,
    ListAPIView,
    ListCreateAPIView,
    UpdateAPIView,
)
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from currencies.models import Currency
from roles.models import Role, UserRole
from users.filters import FilterByUser
from users.models import Invite, User
from users.serializers import (
    ChangeDefaultCurrencySerializer,
    ChangeUserRoleSerializer,
    InviteRequestSerializer,
    InviteSeriazlier,
    RegisterSerializer,
    UserLoginSerializer,
    UserSerializer,
)
from users.entities import UserSchema
from workspaces.filters import FilterByWorkspace


class UserList(ListAPIView):
    serializer_class = UserSerializer

    def list(self, request, *args, **kwargs):
        user = request.user
        members = user.active_workspace.members
        output = []
        for member in members.values():
            usr = UserSchema(**member)
            try:
                user_role = UserRole.objects.get(
                    workspace=user.active_workspace, user__uuid=member["uuid"]
                )
                usr.role = user_role.role.name
            except UserRole.DoesNotExist:
                pass
            output.append(usr)
        serializer = self.get_serializer(output, many=True)
        return Response(serializer.data)


class UserAuth(ObtainAuthToken):
    serializer_class = UserLoginSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = authenticate(
            request,
            username=serializer.validated_data["email"],
            password=serializer.validated_data["password"],
        )
        if user is not None:
            # login(request, user)
            token, created = Token.objects.get_or_create(user=user)
            return Response(
                {
                    "token": token.key,
                    "username": user.username,
                    "email": user.email,
                    "currency": user.default_currency.code
                    if user.default_currency
                    else None,
                }
            )
        else:
            return Response(status=status.HTTP_401_UNAUTHORIZED)


class RegisterView(CreateAPIView):
    queryset = User.objects.all()
    permission_classes = (AllowAny,)
    serializer_class = RegisterSerializer


class CurrencyView(UpdateAPIView):
    queryset = Currency.objects.all()
    serializer_class = ChangeDefaultCurrencySerializer
    filter_backends = (FilterByWorkspace,)
    lookup_field = "code"

    def update(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request.user
        currency_code = serializer.validated_data["currency"]
        user.default_currency = self.filter_queryset(self.get_queryset()).get(
            code=currency_code
        )
        user.save(force_update=True, update_fields=("default_currency",))
        return Response(status=status.HTTP_200_OK)


class InviteView(ListCreateAPIView):
    queryset = Invite.objects.all()
    serializer_class = InviteSeriazlier
    filter_backends = (FilterByWorkspace,)

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset()).filter(
            invite_owner=request.user, workspace=request.user.active_workspace
        )

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = InviteRequestSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = InviteRequestSerializer(queryset, many=True)
        return Response(serializer.data)

    def create(self, request, *args, **kwargs):
        data = {}
        try:
            data["invite_reciever"] = User.objects.get(email=request.data["email"])
        except User.DoesNotExist:
            return Response(
                status=status.HTTP_400_BAD_REQUEST,
                data={"message": "Cannot invite this user"},
            )
        data["invite_owner"] = request.user
        data["workspace"] = request.user.active_workspace.uuid
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(
            serializer.data, status=status.HTTP_201_CREATED, headers=headers
        )


class RevokeInviteView(DestroyAPIView):
    queryset = Invite.objects.all()
    filter_backends = (FilterByUser, FilterByWorkspace)
    lookup_field = "uuid"


class ChangeUserRoleView(UpdateAPIView):
    serializer_class = ChangeUserRoleSerializer
    permission_classes = (UserRolePermissions,)

    def update(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            target_user = User.objects.get(uuid=kwargs.get("uuid"))
            target_role = Role.objects.get(name=serializer.validated_data["role"])
        except User.DoesNotExist:
            return Response("User not found", status=status.HTTP_404_NOT_FOUND)
        except Role.DoesNotExist:
            return Response("Role not found", status=status.HTTP_404_NOT_FOUND)
        user = request.user
        UserRole.objects.update_or_create(
            user=target_user,
            workspace=user.active_workspace,
            defaults={"role": target_role},
        )
        return Response(status=status.HTTP_200_OK)


class UserPermissions(ListAPIView):
    def list(self, request, *args, **kwargs):
        permissions = {
            "add_user": request.user.has_perm("auth.add_user"),
            "can_add_account": request.user.has_perm("auth.add_account"),
            "can_edit_account": request.user.has_perm("auth.update_account"),
            "can_delete_account": request.user.has_perm("auth.delete_account"),
        }
        return Response(permissions)
