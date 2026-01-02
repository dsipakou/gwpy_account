from rest_framework import serializers

from roles.models import Role


class RolesSerializer(serializers.ModelSerializer):
    class Meta:
        model = Role
        fields = ("name",)
