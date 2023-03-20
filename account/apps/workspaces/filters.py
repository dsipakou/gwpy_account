class FilterByWorkspace:
    def filter_queryset(self, request, queryset, view):
        user = request.user

        return queryset.filter(uuid=user.active_workspace)
