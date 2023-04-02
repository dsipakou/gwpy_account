class FilterByWorkspace:
    def filter_queryset(self, request, queryset, view):
        user = request.user

        return queryset.filter(workspace=user.active_workspace.uuid)
