class FilterByUser:
    def filter_queryset(self, request, queryset, view):
        user = request.user

        return queryset.filter(user=user)
