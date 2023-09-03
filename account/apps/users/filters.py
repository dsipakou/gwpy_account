from rest_framework.filters import BaseFilterBackend


class FilterByUser(BaseFilterBackend):
    def filter_queryset(self, request, queryset, view):
        user = request.user

        if user == user.active_workspace.owner:
            return queryset

        return queryset.filter(user=user)
