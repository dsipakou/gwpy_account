from rest_framework.permissions import BasePermission


class BaseWorkspacePermission(BasePermission):
    def has_object_permission(self, request, view, obj):
        user = request.user
        return obj.workspace.owner == user or obj.workspace.members.filter(uuid=user.uuid).exists()
