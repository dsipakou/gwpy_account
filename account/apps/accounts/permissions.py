from rest_framework.permissions import BasePermission
from users import constants


class BaseAccountPermission(BasePermission):
    def has_object_permission(self, request, view, obj):
        user = request.user
        workspace = obj.workspace

        if request.method in constants.SAFE_METHODS:
            return user == obj.user or user.is_owner(workspace)
        if request.method in constants.CREATE_METHODS:
            return user.is_owner(workspace) or user.is_admin(workspace)
        if request.method in constants.EDIT_METHODS:
            return user == obj.user or user.is_owner(workspace)
        if request.method in constants.DELETE_METHODS:
            return user == obj.user or user.is_owner(workspace)
        return False
