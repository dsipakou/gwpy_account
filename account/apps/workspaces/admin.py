from django.contrib import admin

from workspaces.models import Workspace


class WorkspaceAdmin(admin.ModelAdmin):
    list_display = ("uuid", "name", "owner")


admin.site.register(Workspace, WorkspaceAdmin)
