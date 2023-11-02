from currencies.models import Currency
from django.contrib.auth import authenticate
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.generics import CreateAPIView, ListAPIView, UpdateAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from users.filters import FilterByUser
from users.models import Invite, User
from users.serializers import (ChangeDefaultCurrencySerializer,
                               RegisterSerializer, UserLoginSerializer,
                               UserSerializer, InviteSeriazlier)
from workspaces.filters import FilterByWorkspace


class UserList(ListAPIView):
    serializer_class = UserSerializer

    def list(self, request, *args, **kwargs):
        members = request.user.active_workspace.members
        serializer = self.get_serializer(members, many=True)
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
    filter_backends = (FilterByUser, FilterByWorkspace)
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


class InviteView(CreateAPIView):
    queryset = Invite.objects.all()
    serializer_class = InviteSeriazlier

    def create(self, request, *args, **kwargs):
        data = {}
        try:
            data["invite_reciever"] = User.objects.get(email=request.data["email"])
        except User.DoesNotExist:
            return Response(status=status.HTTP_400_BAD_REQUEST, data={"message": "This user does not exist"})
        data["invite_owner"] = request.user
        data["workspace"] = request.user.active_workspace.uuid
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
