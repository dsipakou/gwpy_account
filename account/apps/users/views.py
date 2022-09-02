from rest_framework import status
from rest_framework.authentication import TokenAuthentication
from rest_framework.authtoken.models import Token
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.generics import ListAPIView, UpdateAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from users.models import User
from users.serializers import (ChangeDefaultCurrencySerializer,
                               UserLoginSerializer, UserSerializer)


class UserList(ListAPIView):
    queryset = User.objects.all()
    serializer_class = UserSerializer


class UserAuth(ObtainAuthToken):
    serializer_class = UserLoginSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = User.objects.get(email=serializer.validated_data["email"])
        token, created = Token.objects.get_or_create(user=user)
        return Response(
            {
                "token": token.key,
                "username": user.username,
                "email": user.email,
            }
        )


class CurrencyView(UpdateAPIView):
    authentication_classes = (TokenAuthentication,)
    permission_classes = (IsAuthenticated,)
    serializer_class = ChangeDefaultCurrencySerializer

    def update(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request.user
        user.default_currency = serializer.validated_data["default_currency"]
        user.save(force_update=True, update_fields=("default_currency",))
        return Response(status=status.HTTP_200_OK)
