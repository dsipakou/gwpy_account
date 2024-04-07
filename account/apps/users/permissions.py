from rest_framework.permissions import BasePermission


class BaseUserPermission(BasePermission):
    def has_object_permission(self, request, view, obj):
        user = request.user
        return user == obj.user or obj.workspace.owner == user


class UserRolePermissions(BasePermission):
    def has_permission(self, request, view):
        return request.user.active_workspace.owner == request.user
