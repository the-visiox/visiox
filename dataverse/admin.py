from django.contrib import admin

from dataverse.models import DataverseProject


@admin.register(DataverseProject)
class DataverseProjectAdmin(admin.ModelAdmin):
    list_display = ['title', 'source_project', 'owner', 'is_public', 'fork_count', 'updated_at']
    list_filter = ['is_public', 'license', 'updated_at']
    search_fields = ['title', 'summary', 'source_project__name', 'owner__username', 'owner__email']
    readonly_fields = ['fork_count', 'view_count', 'created_at', 'updated_at']

