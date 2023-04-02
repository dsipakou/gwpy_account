from accounts.models import Account
from accounts.permissions import BaseAccountPermission
from accounts.serializers import AccountSerializer
from rest_framework.generics import (ListCreateAPIView,
                                     RetrieveUpdateDestroyAPIView)


class AccountList(ListCreateAPIView):
    serializer_class = AccountSerializer

    def get_queryset(self):
        user = self.request.user
        workspace = user.active_workspace
        if user == workspace.owner:
            return Account.objects.filter(workspace=workspace)

        return Account.objects.filter(user=user)


class AccountDetails(RetrieveUpdateDestroyAPIView):
    queryset = Account.objects.all()
    serializer_class = AccountSerializer
    lookup_field = "uuid"
    permission_classes = (BaseAccountPermission,)
