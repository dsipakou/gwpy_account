from rest_framework.generics import ListAPIView

from roles.models import Role
from roles.serializers import RolesSerializer


class RolesList(ListAPIView):
    queryset = Role.objects.all()
    serializer_class = RolesSerializer
