from rest_framework.permissions import BasePermission

class AccountPermissions(BasePermission):
    def has_read_permission(self, request, view, obj):
        return obj.is_workspace_member(request.user)
