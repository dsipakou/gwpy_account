from accounts.models import Account
from accounts.permissions import BaseAccountPermission
from accounts.serializers import AccountReassignSerializer, AccountSerializer
from rest_framework import status
from rest_framework.generics import (
    CreateAPIView,
    ListCreateAPIView,
    RetrieveUpdateDestroyAPIView,
    ValidationError,
)
from rest_framework.response import Response
from transactions.models import Transaction
from users.filters import FilterByUser
from users.permissions import BaseUserPermission
from workspaces.filters import FilterByWorkspace


class AccountList(ListCreateAPIView):
    queryset = Account.objects.order_by("-is_main", "created_at")
    serializer_class = AccountSerializer
    permission_classes = (BaseUserPermission,)
    filter_backends = (FilterByUser, FilterByWorkspace)


class AccountDetails(RetrieveUpdateDestroyAPIView):
    queryset = Account.objects.all()
    serializer_class = AccountSerializer
    lookup_field = "uuid"
    permission_classes = (BaseAccountPermission,)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if Transaction.objects.filter(account=instance).exists():
            return Response(
                status=status.HTTP_403_FORBIDDEN,
                data={"error": "This category has at least one transaction"},
            )

        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)


class AccountReassignView(CreateAPIView):
    serializer_class = AccountReassignSerializer
    permission_classes = (BaseAccountPermission,)

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid()
        source_account_uuid = kwargs.get("uuid")
        dest_account_uuid = serializer.validated_data["account"]
        if source_account_uuid == dest_account_uuid:
            raise ValidationError("Cannot reassign to the same account")

        transactions = Transaction.objects.filter(account__uuid=source_account_uuid)
        transactions.update(account=dest_account_uuid)
        return Response(status=status.HTTP_200_OK)
