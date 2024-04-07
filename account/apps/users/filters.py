from rest_framework.filters import BaseFilterBackend


class FilterByUser(BaseFilterBackend):
    def filter_queryset(self, request, queryset, view):
        user = request.user
        workspace = user.active_workspace

        if user == user.active_workspace.owner or user.is_admin(workspace):
            return queryset

        return queryset.filter(user=user)


class FilterInviteByUser(BaseFilterBackend):
    def filter_queryset(self, request, queryset, view):
        user = request.user

        if user == user.active_workspace.owner:
            return queryset

        return queryset.filter(user=user)
