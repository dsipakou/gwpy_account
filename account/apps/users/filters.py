class FilterByUser:
    def filter_queryset(self, request, queryset, view):
        user = request.user
        queryset = queryset.filter(workspace=user.active_workspace)

        if user == user.active_workspace.owner:
            return queryset

        return queryset.filter(user=user)
